#!/bin/sh -i

export STORAGE_DOMAIN
export PYTHONWARNINGS="ignore:Unverified HTTPS request"

REDIS_WORKERS=${REDIS_WORKERS:-1}

if [ "${REDIS_WORKERS}" -eq 0 ]
then
    echo "REDIS_WORKERS is set to 0, not starting any workers, sleeping forever"
    sleep infinity
fi

# --- Phase-1 queue tiering: reserved + standard-lane + elastic pools ---------
#
# Latency isolation comes from partitioning the worker fleet by tier and from a
# resource governor on the heavy tier (see docs/superpowers/specs/
# 2026-07-01-queue-worker-dimensioning-design.md §3.3 / §5.7):
#
#   * RESERVED workers  -> [interactive] ONLY. Sub-second click-and-wait work
#     (desktop create / non-persistent start's volatile create / recreate).
#     Nothing longer can ever occupy them (non-preemption), so a create/start
#     stays fast independent of any resize/template/bulk/maintenance storm.
#   * STANDARD-LANE      -> [standard, interactive]. Single foreground ops that
#     are seconds-not-subsecond (disk resize, virt_win_reg). Kept OFF the
#     reserved pool so a resize can never block a create/start, and so a long
#     standard op can't block interactive.
#   * TEMPLATE-LANE (governed) -> [template, bulk, maintenance, reclaim]. A
#     dedicated governed worker for template-from-desktop whole-disk copies, so
#     a burst of quick bulk creates can never block a template (and vice-versa);
#     work-conserving — it helps drain bulk/maintenance/reclaim when idle.
#   * ELASTIC (governed) -> [bulk, maintenance, reclaim, template, foreground
#     overflow]. Runs a GovernedWorker: a heavy task (template/maintenance/
#     reclaim) is admitted only when the node has CPU/IO headroom (Linux PSI)
#     and heavy concurrency is under cap, so heavy work is packed into low-load
#     troughs and never overloads the node or steals capacity from bulk.
#   * BG-FLOOR (ungoverned) -> [maintenance, reclaim, bulk, template, ...].
#     Always runs >=1 heavy task so a permanently-busy foreground can never
#     fully starve the maintenance/reclaim backlog.
#
# Legacy high/default/low queues are drained by the elastic/bg-floor pools only.
# Fixed counts (no autoscaler yet). REDIS_WORKERS is the total fleet budget; the
# elastic pool absorbs whatever is left after the fixed pools, so the total is
# MONOTONIC in REDIS_WORKERS:
#   total = RESERVED + STDLANE + TEMPLATE + ELASTIC + 1 (bg-floor)
#   STORAGE_RESERVED_WORKERS (default 2)  STORAGE_STANDARD_WORKERS (default 1)
#   STORAGE_TEMPLATE_WORKERS (default 1; 0 drops the lane -> template falls to elastic)
#   STORAGE_ELASTIC_WORKERS  (default: REDIS_WORKERS - reserved - std - template - 1, floored at 1)
# The tiered fleet has a MINIMUM size of reserved + std + template + 1 elastic +
# 1 bg-floor (6 with defaults); below that, REDIS_WORKERS cannot be honoured
# exactly — shrink a pool with STORAGE_*_WORKERS (e.g. =1, or =0 to drop it) on
# tiny installs.
# Governor knobs: STORAGE_GOVERNOR_PSI_LIMIT (40), STORAGE_GOVERNOR_MAX_HEAVY (2).
RESERVED_WORKERS=${STORAGE_RESERVED_WORKERS:-2}
STDLANE_WORKERS=${STORAGE_STANDARD_WORKERS:-1}
TEMPLATE_WORKERS=${STORAGE_TEMPLATE_WORKERS:-1}
BGFLOOR_WORKERS=1
if [ -n "${STORAGE_ELASTIC_WORKERS}" ]; then
    ELASTIC_WORKERS=${STORAGE_ELASTIC_WORKERS}
else
    ELASTIC_WORKERS=$((REDIS_WORKERS - RESERVED_WORKERS - STDLANE_WORKERS - TEMPLATE_WORKERS - BGFLOOR_WORKERS))
    [ "${ELASTIC_WORKERS}" -lt 1 ] && ELASTIC_WORKERS=1
fi

GOVERNED_WORKER_CLASS="isardvdi_common.lib.governed_worker.GovernedWorker"

# Build a space-separated queue list for a set of tiers, honouring the pool sort
# order and the cross-pool storage.<src>:<dst>.<tier> move queues.
build_tier_queues() {
    _out=""
    for _tier in "$@"; do
        _previous_pools=""
        for _pool in $(echo ${CAPABILITIES_STORAGE_POOLS:-00000000-0000-0000-0000-000000000000} | tr "," "\n" | sort); do
            _out="$_out storage.$_pool.$_tier"
            for _previous_pool in $_previous_pools; do
                _out="$_out storage.$_previous_pool:$_pool.$_tier"
            done
            _previous_pools="$_previous_pools $_pool"
        done
    done
    echo "$_out"
}

# Worker bookkeeping for the supervisor: each spawned worker's PID, spawn time
# and its full spec (role + worker-class + queues) are recorded so a dead worker
# can be respawned as the SAME pool with the SAME subscription and mode.
declare -A spawn_at
declare -A worker_spec
worker_pids=""

# start_worker <role> <worker-class-or-"-"> <queues...>
start_worker() {
    _role="$1"
    _wclass="$2"
    shift 2
    _class_arg=""
    [ "${_wclass}" != "-" ] && _class_arg="--worker-class ${_wclass}"
    # bg-floor runs the GovernedWorker ungoverned (FLOOR mode). Setting it per
    # worker process (not via a shell-scoped export) keeps first-start and
    # supervisor respawn identical -- a respawned bg-floor stays a floor worker.
    _floor_env=""
    [ "${_role}" = "bgfloor" ] && _floor_env="STORAGE_GOVERNOR_FLOOR=true"
    env ${_floor_env} rq worker \
        --connection-class="isardvdi_common.connections.redis_retry.RedisRetry" \
        --url "redis://:${REDIS_PASSWORD}@${REDIS_HOST:-isard-redis}:${REDIS_PORT:-6379}/0" \
        --path /opt/isardvdi/isardvdi_task \
        --logging_level ${LOG_LEVEL:-INFO} \
        --with-scheduler \
        ${_class_arg} \
        --name storage-${_role}:${STORAGE_DOMAIN:-isard-storage}:$(uuidgen) \
        "$@" &
    worker_pids="${worker_pids} $!"
    spawn_at[$!]=${EPOCHSECONDS}
    worker_spec[$!]="${_role} ${_wclass} $*"
}

if ${CAPABILITIES_DISK:-true}
then
    # Wait for Redis to be ready before starting workers
    /utils/wait_for_redis

    # Queue subscription order per pool (RQ serves queues in the order listed).
    RESERVED_QUEUES=$(build_tier_queues interactive)
    STDLANE_QUEUES=$(build_tier_queues standard interactive)
    # Template-lane: template FIRST (its reason to exist), then help drain the
    # other governed tiers when no template is queued (work-conserving). background
    # (idle metadata refreshes) is the lowest, drained only when nothing else.
    TEMPLATE_QUEUES=$(build_tier_queues template bulk maintenance reclaim background)
    # Elastic: bulk throughput first, then the heavy tiers, then template (the
    # template-lane leads on those), then foreground overflow + legacy lanes, and
    # LAST the idle background lane (served only when the worker is otherwise idle).
    ELASTIC_QUEUES=$(build_tier_queues bulk maintenance reclaim template interactive standard high default low background)
    # Bg-floor: maintenance/reclaim FIRST so the lowest tiers never fully starve;
    # background is last (idle-only lifecycle metadata refreshes).
    BGFLOOR_QUEUES=$(build_tier_queues maintenance reclaim bulk template interactive standard high default low background)

    echo "storage tiering: ${RESERVED_WORKERS} reserved(interactive) + ${STDLANE_WORKERS} std-lane(standard) + ${TEMPLATE_WORKERS} template-lane(governed template) + ${ELASTIC_WORKERS} elastic(governed bulk/maintenance/reclaim/background) + ${BGFLOOR_WORKERS} bg-floor (REDIS_WORKERS=${REDIS_WORKERS})"

    # Graceful shutdown: on TERM/INT stop supervising and forward the signal to
    # every worker so each finishes its current job (rq warm shutdown) and exits.
    shutting_down=0
    shutdown() {
        shutting_down=1
        kill -TERM ${worker_pids} 2>/dev/null
    }
    trap shutdown TERM INT

    # A pool count of 0 drops that pool (guard: seq semantics vary for 0/reverse).
    _n=0; while [ "${_n}" -lt "${RESERVED_WORKERS}" ]; do start_worker reserved - $RESERVED_QUEUES; _n=$((_n + 1)); done
    _n=0; while [ "${_n}" -lt "${STDLANE_WORKERS}" ]; do start_worker stdlane - $STDLANE_QUEUES; _n=$((_n + 1)); done
    _n=0; while [ "${_n}" -lt "${TEMPLATE_WORKERS}" ]; do start_worker template "${GOVERNED_WORKER_CLASS}" $TEMPLATE_QUEUES; _n=$((_n + 1)); done
    _n=0; while [ "${_n}" -lt "${ELASTIC_WORKERS}" ]; do start_worker elastic "${GOVERNED_WORKER_CLASS}" $ELASTIC_QUEUES; _n=$((_n + 1)); done
    # bg-floor: FLOOR mode — runs the GovernedWorker but ungoverned (never
    # defers/caps/reserves), so >=1 heavy task always progresses AND, under
    # STORAGE_QUEUE_MULTITENANCY, it discovers and serves the per-category lanes
    # too (else category heavy work could starve while the flat lane sits idle).
    # With multitenancy off this is behaviourally identical to the old stock
    # bg-floor draining the flat queues. (FLOOR mode is set per-process in
    # start_worker so a respawn preserves it.)
    _n=0; while [ "${_n}" -lt "${BGFLOOR_WORKERS}" ]; do start_worker bgfloor "${GOVERNED_WORKER_CLASS}" $BGFLOOR_QUEUES; _n=$((_n + 1)); done

    # Crash-loop guard (respawn backoff): a worker that dies within
    # WORKER_MIN_UPTIME_S of being spawned is treated as a likely persistent
    # startup failure. Each consecutive fast death adds RESPAWN_BACKOFF_STEP_S of
    # delay before respawning, capped at RESPAWN_BACKOFF_MAX_S. A worker that ran
    # healthily (lifetime >= WORKER_MIN_UPTIME_S) resets the counter and respawns
    # promptly -- the happy path adds NO latency.
    WORKER_MIN_UPTIME_S=5
    RESPAWN_BACKOFF_STEP_S=2
    RESPAWN_BACKOFF_MAX_S=30
    fast_deaths=0

    # Supervisor: a worker subprocess that dies (kill -9, OOM, crash) MUST be
    # replaced -- if it was a tier's only consumer that lane stalls until the job
    # timeout, and no live worker runs rq's clean_registries to reap abandoned
    # STARTED jobs. Respawn a FRESH worker with the dead one's ORIGINAL spec so the
    # pool layout (reserved / std-lane / template / elastic / bg-floor) and mode
    # are preserved. Only the dead worker is replaced; healthy siblings keep
    # running their in-flight tasks undisturbed.
    while [ "${shutting_down}" -eq 0 ]; do
        dead_pid=""
        wait -n -p dead_pid
        [ "${shutting_down}" -eq 1 ] && break
        # Respawn only when one of OUR tracked workers exited (ignore rq's
        # transient scheduler/work-horse forks that bash may surface here).
        if [ -n "${dead_pid}" ]; then
            case " ${worker_pids} " in
                *" ${dead_pid} "*)
                    worker_pids="$(echo " ${worker_pids} " | sed "s/ ${dead_pid} / /")"
                    lifetime=$(( EPOCHSECONDS - ${spawn_at[${dead_pid}]:-0} ))
                    dead_spec="${worker_spec[${dead_pid}]}"
                    unset "spawn_at[${dead_pid}]"
                    unset "worker_spec[${dead_pid}]"
                    if [ "${lifetime}" -lt "${WORKER_MIN_UPTIME_S}" ]; then
                        fast_deaths=$(( fast_deaths + 1 ))
                        backoff=$(( fast_deaths * RESPAWN_BACKOFF_STEP_S ))
                        [ "${backoff}" -gt "${RESPAWN_BACKOFF_MAX_S}" ] && backoff=${RESPAWN_BACKOFF_MAX_S}
                        echo "init.sh: storage worker ${dead_pid} died after ${lifetime}s (fast, ${fast_deaths} in a row); backing off ${backoff}s before respawn"
                        sleep "${backoff}"
                        [ "${shutting_down}" -eq 1 ] && break
                    else
                        fast_deaths=0
                    fi
                    start_worker ${dead_spec}
                    echo "init.sh: storage worker ${dead_pid} (${dead_spec%% *}) exited; respawned a fresh one"
                    ;;
            esac
        fi
    done

    # Drain: let the workers we signalled finish their warm shutdown.
    wait
else
    sleep infinity
fi
