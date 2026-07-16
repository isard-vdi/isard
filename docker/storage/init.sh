#!/bin/bash -i

export STORAGE_DOMAIN
export PYTHONWARNINGS="ignore:Unverified HTTPS request"

REDIS_WORKERS=${REDIS_WORKERS:-1}

if [ "${REDIS_WORKERS}" -eq 0 ]
then
    echo "REDIS_WORKERS is set to 0, not starting any workers, sleeping forever"
    sleep infinity
fi

if ${CAPABILITIES_DISK:-true}
then
    # Wait for Redis to be ready before starting workers
    /utils/wait_for_redis

    for priority in high default low; do
        previous_pools=""

        for pool in $(echo ${CAPABILITIES_STORAGE_POOLS:-00000000-0000-0000-0000-000000000000} | tr "," "\n" | sort); do
            queues="$queues storage.$pool.$priority"

            for previous_pool in $previous_pools; do
                queues="$queues storage.$previous_pool:$pool.$priority"
            done

            previous_pools="$previous_pools $pool"
        done
    done

    # Start one rq worker (background job). Every worker consumes ALL queues and,
    # on startup and then every maintenance interval, runs rq's clean_registries,
    # which reaps abandoned STARTED jobs -- those whose worker died and stopped
    # refreshing their heartbeat score -- to FAILED (AbandonedJobError).
    #
    # Each spawned worker's PID and spawn time are recorded (worker_pids +
    # spawn_at) so the supervisor reacts ONLY to our workers dying and can
    # rate-limit a worker that dies right after starting (crash-loop guard).
    declare -A spawn_at
    start_worker() {
        rq worker \
            --connection-class="isardvdi_common.connections.redis_retry.RedisRetry" \
            --url "redis://:${REDIS_PASSWORD}@${REDIS_HOST:-isard-redis}:${REDIS_PORT:-6379}/0" \
            --path /opt/isardvdi/isardvdi_task \
            --logging_level ${LOG_LEVEL:-INFO} \
            --with-scheduler \
            --name storage:${STORAGE_DOMAIN:-isard-storage}:$(uuidgen) \
            $queues &
        worker_pids="${worker_pids} $!"
        spawn_at[$!]=${EPOCHSECONDS}
    }

    # Graceful shutdown: on TERM/INT stop supervising and forward the signal to
    # every worker so each finishes its current job (rq warm shutdown) and exits.
    shutting_down=0
    shutdown() {
        shutting_down=1
        kill -TERM ${worker_pids} 2>/dev/null
    }
    trap shutdown TERM INT

    # Start the workers, tracking each background worker's PID. We react ONLY to a
    # tracked worker dying: rq's --with-scheduler forks short-lived children that
    # bash also surfaces via `wait -n`, and respawning on those would leak workers.
    worker_pids=""
    for _ in $(seq 1 ${REDIS_WORKERS}); do
        start_worker
    done

    # Crash-loop guard (respawn backoff): a worker that dies within
    # WORKER_MIN_UPTIME_S of being spawned is treated as a likely persistent
    # startup failure (bad config, import error). Each consecutive fast death
    # adds RESPAWN_BACKOFF_STEP_S of delay before respawning, capped at
    # RESPAWN_BACKOFF_MAX_S, so a hard crash-loop does not churn. A worker that
    # ran healthily before dying (lifetime >= WORKER_MIN_UPTIME_S) resets the
    # counter and respawns promptly -- the happy path adds NO latency.
    WORKER_MIN_UPTIME_S=5
    RESPAWN_BACKOFF_STEP_S=2
    RESPAWN_BACKOFF_MAX_S=30
    fast_deaths=0

    # Supervisor: a worker subprocess that dies (kill -9, OOM, crash) MUST be
    # replaced. Previously PID 1 only ran `sleep infinity`, so a dead worker was
    # never restarted: Docker kept the container "healthy", and if the dead
    # worker was a queue's only consumer no live worker ever ran clean_registries,
    # so an abandoned STARTED job stalled until the 12h job timeout. Respawning a
    # FRESH worker keeps every queue consumed and makes that fresh worker reap
    # abandoned jobs (fail-not-resume) on startup and on its maintenance interval.
    # Only the dead worker is replaced; healthy siblings keep running their
    # in-flight tasks undisturbed.
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
                    # Crash-loop guard: if this worker died very soon after it was
                    # spawned it is likely failing on startup; back off before the
                    # respawn so a hard crash-loop does not churn. A worker that ran
                    # healthily (lifetime >= WORKER_MIN_UPTIME_S) resets the counter
                    # and respawns immediately.
                    lifetime=$(( EPOCHSECONDS - ${spawn_at[${dead_pid}]:-0} ))
                    unset "spawn_at[${dead_pid}]"
                    if [ "${lifetime}" -lt "${WORKER_MIN_UPTIME_S}" ]; then
                        fast_deaths=$(( fast_deaths + 1 ))
                        backoff=$(( fast_deaths * RESPAWN_BACKOFF_STEP_S ))
                        [ "${backoff}" -gt "${RESPAWN_BACKOFF_MAX_S}" ] && backoff=${RESPAWN_BACKOFF_MAX_S}
                        echo "init.sh: storage worker ${dead_pid} died after ${lifetime}s (fast, ${fast_deaths} in a row); backing off ${backoff}s before respawn"
                        sleep "${backoff}"
                        # A shutdown signal may have arrived during the backoff.
                        [ "${shutting_down}" -eq 1 ] && break
                    else
                        fast_deaths=0
                    fi
                    start_worker
                    echo "init.sh: storage worker ${dead_pid} exited; respawned a fresh one"
                    ;;
            esac
        fi
    done

    # Drain: let the workers we signalled finish their warm shutdown.
    wait
else
    sleep infinity
fi
