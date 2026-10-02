#!/bin/bash
#
# IsardVDI - On-demand Prometheus -> VictoriaMetrics metrics migration
#
# Imports the historic Prometheus TSDB into the running VictoriaMetrics. It is a
# separate admin action, run ON DEMAND outside the upgrade window: on a monitor
# with real retention the import takes hours.
#
# What it does (idempotent -- a marker guards against re-running):
#   1. Refuses to start when the live VictoriaMetrics retention would discard
#      part of the history being imported (see --trim-to-retention).
#   2. Builds a working copy of the Prometheus TSDB (immutable blocks are hard
#      links, the WAL is copied) and snapshots it with a throwaway Prometheus
#      that has no scrape targets and no retention. The original TSDB is never
#      opened by any process.
#   3. Imports the snapshot with vmctl straight into the live
#      isard-victoriametrics, which keeps running, up to the first sample it
#      already holds, so the imported history neither overlaps nor duplicates
#      the metrics collected since the upgrade.
#   4. Checks that VictoriaMetrics answers for the imported days, and only then
#      archives the old Prometheus data and drops the marker.
#
# Usage:
#   sudo bash sysadm/migrate-prometheus-to-victoriametrics.sh                       # migrate
#   sudo bash sysadm/migrate-prometheus-to-victoriametrics.sh --force               # skip the free-space check
#   sudo bash sysadm/migrate-prometheus-to-victoriametrics.sh --trim-to-retention   # import only what the retention keeps
#   sudo bash sysadm/migrate-prometheus-to-victoriametrics.sh --help
#
# Background (recommended -- it can run for hours):
#   sudo nohup bash sysadm/migrate-prometheus-to-victoriametrics.sh \
#       >/opt/isard/migrate-prometheus-to-victoriametrics.log 2>&1 &
#
# Environment overrides:
#   ISARD_DIR   install dir holding docker-compose-parts/ (default: autodetected, else /opt/isard)
#   STATS_DIR   metrics data dir (default: derived from monitor.yml, else /opt/isard/stats)
#   PROMETHEUS_READY_TIMEOUT_SECONDS        how long to wait for the temporary Prometheus to
#                                           replay its WAL before snapshotting (default: 1800)
#
set -eu

PROMETHEUS_READY_TIMEOUT_SECONDS=${PROMETHEUS_READY_TIMEOUT_SECONDS:-1800}

FORCE=0
TRIM=0
for arg in "$@"; do
	case "$arg" in
	--force) FORCE=1 ;;
	--trim-to-retention) TRIM=1 ;;
	-h | --help)
		sed -n '2,37p' "$0" | sed 's/^# \{0,1\}//'
		exit 0
		;;
	*)
		echo "Unknown argument: $arg (try --help)" >&2
		exit 2
		;;
	esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2; }

# Bare numbers are months of 31 days, as VictoriaMetrics counts them.
retention_seconds() {
	case "$1" in
	*[smhdwy]) _num=${1%?} _unit=${1#"${1%?}"} ;;
	*) _num=$1 _unit=M ;;
	esac
	case "$_num" in
	'' | *[!0-9.]*) return 1 ;;
	esac
	case "$_unit" in
	s) _mult=1 ;;
	m) _mult=60 ;;
	h) _mult=3600 ;;
	d) _mult=86400 ;;
	w) _mult=604800 ;;
	y) _mult=31536000 ;;
	M) _mult=2678400 ;;
	esac
	awk -v n="$_num" -v m="$_mult" 'BEGIN { printf "%d", n * m }'
}

iso_utc() { date -u -d "@$1" '+%Y-%m-%dT%H:%M:%SZ'; }

# Use sudo when required (mirrors build.sh)
SUDO=""
if [ "$(id -u)" != 0 ] && command -v sudo >/dev/null 2>&1; then
	SUDO="sudo"
fi

# Locate the install dir (where docker-compose-parts/ lives).
if [ -z "${ISARD_DIR:-}" ]; then
	_self_dir=$(cd "$(dirname "$0")" && pwd)
	if [ -f "$_self_dir/../docker-compose-parts/monitor.yml" ]; then
		ISARD_DIR=$(cd "$_self_dir/.." && pwd)
	else
		ISARD_DIR="/opt/isard"
	fi
fi
MONITOR_YML="$ISARD_DIR/docker-compose-parts/monitor.yml"

# The stats dir is NOT necessarily under ISARD_DIR: the standard layout keeps
# code in /opt/isard/src and data in /opt/isard/stats (a sibling, not a child).
# So $ISARD_DIR/stats would wrongly resolve to /opt/isard/src/stats and the
# migration would silently find nothing. Derive it from the victoriametrics data
# volume declared in monitor.yml, falling back to /opt/isard/stats.
if [ -z "${STATS_DIR:-}" ]; then
	STATS_DIR=$(sed -n 's|[[:space:]]*-[[:space:]]*\(/.*\)/victoriametrics:/victoria-metrics-data.*|\1|p' "$MONITOR_YML" 2>/dev/null | head -1)
	[ -n "$STATS_DIR" ] || STATS_DIR="/opt/isard/stats"
fi

PROMETHEUS_DIR="$STATS_DIR/prometheus"
VICTORIAMETRICS_DIR="$STATS_DIR/victoriametrics"
MARKER="$VICTORIAMETRICS_DIR/.migrated-from-prometheus"
WORK_DIR="$STATS_DIR/prometheus-migrate-work"
EMPTY_CONFIG="$STATS_DIR/prometheus-migrate-empty.yml"
PROMETHEUS_IMAGE="prom/prometheus:v3.5.2"
PROMETHEUS_CONTAINER="isard-prometheus-migrate"
VICTORIAMETRICS_LIVE="isard-victoriametrics"

# --- Idempotency / pre-flight -----------------------------------------------
if [ ! -d "$PROMETHEUS_DIR" ]; then
	log "No Prometheus data at $PROMETHEUS_DIR -- nothing to migrate."
	exit 0
fi
if [ -f "$MARKER" ]; then
	log "Already migrated ($MARKER present) -- nothing to do."
	exit 0
fi
if ! command -v docker >/dev/null 2>&1; then
	err "ERROR: docker not found in PATH."
	exit 1
fi
if [ ! -f "$MONITOR_YML" ]; then
	err "ERROR: $MONITOR_YML not found. Set ISARD_DIR to the install dir and retry."
	exit 1
fi

VICTORIAMETRICS_TAG=$(sed -n 's|.*image: *victoriametrics/victoria-metrics:\([^ ]*\).*|\1|p' "$MONITOR_YML" | head -1)
if [ -z "$VICTORIAMETRICS_TAG" ]; then
	err "ERROR: could not read the VictoriaMetrics image tag from $MONITOR_YML."
	exit 1
fi
# The digest pinned in monitor.yml is victoria-metrics', not vmctl's.
VMCTL_IMAGE="victoriametrics/vmctl:${VICTORIAMETRICS_TAG%%@*}"

if [ -z "$(docker ps -q -f name="^${VICTORIAMETRICS_LIVE}\$" 2>/dev/null)" ]; then
	err "ERROR: $VICTORIAMETRICS_LIVE is not running. Bring the monitor stack up and retry."
	exit 1
fi
VM_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$VICTORIAMETRICS_LIVE" 2>/dev/null || true)
if [ -z "$VM_IP" ] || ! curl -sf "http://$VM_IP:8428/health" >/dev/null 2>&1; then
	err "ERROR: $VICTORIAMETRICS_LIVE does not answer on http://$VM_IP:8428/health."
	exit 1
fi
VM_URL="http://$VM_IP:8428"

# --- Retention check ---------------------------------------------------------
# VictoriaMetrics silently rejects samples older than its retention (default: 1 month).
VM_RETENTION=$(docker inspect -f '{{range .Args}}{{println .}}{{end}}' "$VICTORIAMETRICS_LIVE" | sed -n 's/^--\{0,1\}retentionPeriod=//p' | tail -1)
[ -n "$VM_RETENTION" ] || VM_RETENTION=1
if ! RETENTION_S=$(retention_seconds "$VM_RETENTION"); then
	err "ERROR: could not parse the VictoriaMetrics retention '$VM_RETENTION'."
	exit 1
fi
NOW_S=$(date -u +%s)
KEEP_FROM_S=$((NOW_S - RETENTION_S + 86400))

_oldest_ms=$(find "$PROMETHEUS_DIR" -mindepth 2 -maxdepth 2 -name meta.json -not -path '*/snapshots/*' -not -path '*.tmp*' \
	-exec sed -n 's/.*"minTime":[[:space:]]*\([0-9]*\).*/\1/p' {} + 2>/dev/null | sort -n | head -1)
IMPORT_START_S=""
if [ -n "$_oldest_ms" ]; then
	_oldest_s=$((_oldest_ms / 1000))
	log "Prometheus history starts at $(iso_utc "$_oldest_s"); VictoriaMetrics retention is $VM_RETENTION (keeps from $(iso_utc "$KEEP_FROM_S"))."
	if [ "$_oldest_s" -lt "$KEEP_FROM_S" ]; then
		if [ "$TRIM" != 1 ]; then
			err "ERROR: the Prometheus history is older than the VictoriaMetrics retention ($VM_RETENTION)."
			err "       Importing it now would drop everything before $(iso_utc "$KEEP_FROM_S")."
			err "       Either raise VICTORIAMETRICS_RETENTION_TIME in isardvdi.cfg, run build.sh and"
			err "       recreate isard-victoriametrics, then retry; or re-run with --trim-to-retention"
			err "       to import only what the current retention keeps. Nothing has been changed."
			exit 1
		fi
		IMPORT_START_S=$KEEP_FROM_S
		err "WARNING: --trim-to-retention: importing only from $(iso_utc "$IMPORT_START_S"); older history stays in the archived Prometheus data."
	fi
fi

# --- Where the live VictoriaMetrics data starts --------------------------------
FIRST_VM_S=""
_day_s=$((NOW_S - NOW_S % 86400))
_first_day_s=""
_days=0
while [ "$_day_s" -ge "$KEEP_FROM_S" ] && [ "$_days" -le 3660 ]; do
	_series=$(curl -sf --get "$VM_URL/api/v1/status/tsdb" --data-urlencode "date=$(date -u -d "@$_day_s" +%Y-%m-%d)" --data-urlencode "topN=1" 2>/dev/null |
		sed -n 's/.*"totalSeries":\([0-9]*\).*/\1/p')
	[ "${_series:-0}" -gt 0 ] || break
	_first_day_s=$_day_s
	_day_s=$((_day_s - 86400))
	_days=$((_days + 1))
done
if [ -n "$_first_day_s" ]; then
	_tries=0
	while [ -z "$FIRST_VM_S" ] && [ "$_tries" -lt 12 ]; do
		[ "$_tries" -gt 0 ] && sleep 5
		FIRST_VM_S=$(curl -sf --get "$VM_URL/api/v1/query" \
			--data-urlencode 'query=min(tfirst_over_time({__name__=~"up|vm_app_version"}[2d]))' \
			--data-urlencode "time=$((_first_day_s + 2 * 86400))" 2>/dev/null |
			sed -n 's/.*"value":\[[^,]*,"\([0-9]*\)[.0-9]*".*/\1/p')
		_tries=$((_tries + 1))
	done
	# A gap of under a day is preferable to duplicated samples.
	[ -n "$FIRST_VM_S" ] || FIRST_VM_S=$_first_day_s
	log "The live VictoriaMetrics holds data from $(iso_utc "$FIRST_VM_S"); the import stops just before it."
else
	log "The live VictoriaMetrics holds no data yet; the whole history will be imported."
fi

# --- Free-space check --------------------------------------------------------
_src_kb=$(du -sk "$PROMETHEUS_DIR" 2>/dev/null | awk '{print $1}')
_avail_kb=$(df -Pk "$STATS_DIR" | awk 'NR==2 {print $4}')
_src_h=$(awk -v k="${_src_kb:-0}" 'BEGIN{printf "%.1f", k/1048576}')
_avail_h=$(awk -v k="${_avail_kb:-0}" 'BEGIN{printf "%.1f", k/1048576}')
log "Prometheus data: ${_src_h} GiB   free on $(df -Pk "$STATS_DIR" | awk 'NR==2{print $6}'): ${_avail_h} GiB"
if [ "${_avail_kb:-0}" -lt "${_src_kb:-0}" ]; then
	if [ "$FORCE" != 1 ]; then
		err "ERROR: not enough free space (need >= ${_src_h} GiB, have ${_avail_h} GiB). Free space or re-run with --force."
		exit 1
	fi
	err "WARNING: free space below the recommended threshold; continuing because --force was given."
fi

# --- Migration ---------------------------------------------------------------
MIGRATED=0
IMPORT_STARTED=0

cleanup() {
	docker rm -f "$PROMETHEUS_CONTAINER" >/dev/null 2>&1 || true
	$SUDO rm -rf "$WORK_DIR" "$EMPTY_CONFIG" || true
}
trap cleanup EXIT INT TERM

log "Migrating Prometheus metrics at $PROMETHEUS_DIR into the live VictoriaMetrics ($VICTORIAMETRICS_TAG)..."

docker rm -f "$PROMETHEUS_CONTAINER" >/dev/null 2>&1 || true
# A legacy isard-prometheus still writing to the TSDB would make the copy inconsistent.
docker stop isard-prometheus >/dev/null 2>&1 || true

while :; do
	log "Preparing a working copy of the Prometheus TSDB at $WORK_DIR..."
	$SUDO rm -rf "$WORK_DIR"
	$SUDO mkdir -p "$WORK_DIR"
	_copy_ok=1
	for _entry in "$PROMETHEUS_DIR"/* "$PROMETHEUS_DIR"/.[!.]*; do
		[ -e "$_entry" ] || continue
		case "${_entry##*/}" in
		snapshots | lock | queries.active) ;;
		# Written in place while the WAL is replayed: a real copy, never a link.
		wal | chunks_head) $SUDO cp -a "$_entry" "$WORK_DIR/" || _copy_ok=0 ;;
		*) $SUDO cp -al "$_entry" "$WORK_DIR/" || _copy_ok=0 ;;
		esac
	done
	if [ "$_copy_ok" != 1 ]; then
		err "ERROR: could not prepare the working copy of the Prometheus TSDB."
		break
	fi
	printf 'global: {}\n' | $SUDO tee "$EMPTY_CONFIG" >/dev/null

	log "Starting a temporary Prometheus on the working copy to snapshot it..."
	if ! docker run -d --name "$PROMETHEUS_CONTAINER" --user root \
		-v "$WORK_DIR:/prometheus" -v "$EMPTY_CONFIG:/etc/prometheus/migrate.yml:ro" "$PROMETHEUS_IMAGE" \
		--config.file=/etc/prometheus/migrate.yml \
		--storage.tsdb.path=/prometheus --storage.tsdb.retention.time=100y \
		--web.enable-admin-api >/dev/null; then
		err "ERROR: could not start the temporary Prometheus."
		break
	fi

	_prometheus_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$PROMETHEUS_CONTAINER" 2>/dev/null || true)
	if [ -z "$_prometheus_ip" ]; then
		err "ERROR: could not resolve the temporary Prometheus IP."
		break
	fi

	# Prometheus replays its whole write-ahead log before serving the admin API, and
	# that scales with the TSDB: a multi-tens-of-GiB store needs several minutes, so a
	# short fixed wait aborts the migration on exactly the installs that need it most.
	# Poll /-/ready (503 while replaying) instead of hammering the snapshot endpoint.
	log "Waiting for the temporary Prometheus to replay its WAL (timeout ${PROMETHEUS_READY_TIMEOUT_SECONDS}s)..."
	_ready=0
	_waited=0
	while [ "$_waited" -lt "$PROMETHEUS_READY_TIMEOUT_SECONDS" ]; do
		if curl -sf "http://$_prometheus_ip:9090/-/ready" >/dev/null 2>&1; then
			_ready=1
			break
		fi
		_waited=$((_waited + 5))
		sleep 5
	done
	if [ "$_ready" != 1 ]; then
		err "ERROR: the temporary Prometheus was not ready after ${PROMETHEUS_READY_TIMEOUT_SECONDS}s."
		err "       Raise PROMETHEUS_READY_TIMEOUT_SECONDS if the WAL replay is still progressing. Its logs:"
		docker logs --tail 20 "$PROMETHEUS_CONTAINER" 2>&1 | sed 's/^/    /' >&2 || true
		break
	fi

	log "Creating a Prometheus snapshot..."
	_snapshot=$(curl -sf -X POST "http://$_prometheus_ip:9090/api/v1/admin/tsdb/snapshot" 2>/dev/null | sed -n 's/.*"name":"\([^"]*\)".*/\1/p')
	if [ -z "$_snapshot" ]; then
		err "ERROR: the temporary Prometheus did not return a snapshot. Its logs:"
		docker logs --tail 20 "$PROMETHEUS_CONTAINER" 2>&1 | sed 's/^/    /' >&2 || true
		break
	fi
	log "Snapshot created: $_snapshot"
	docker rm -f "$PROMETHEUS_CONTAINER" >/dev/null 2>&1 || true

	# No terminal under nohup: the progress bar would make vmctl abort.
	set -- prometheus -s --disable-progress-bar --prom-snapshot=/snapshot --vm-addr="$VM_URL"
	if [ -n "$IMPORT_START_S" ]; then
		set -- "$@" --prom-filter-time-start="$(iso_utc "$IMPORT_START_S")"
	fi
	if [ -n "$FIRST_VM_S" ]; then
		set -- "$@" --prom-filter-time-end="$(iso_utc "$((FIRST_VM_S - 1))")"
	fi
	log "Importing the snapshot into the live VictoriaMetrics with vmctl (this can take a long time)..."
	IMPORT_STARTED=1
	if ! docker run --rm --network host --user root \
		-v "$WORK_DIR/snapshots/$_snapshot:/snapshot:ro" "$VMCTL_IMAGE" "$@"; then
		err "ERROR: vmctl import failed."
		break
	fi
	curl -sf "$VM_URL/internal/resetRollupResultCache" >/dev/null 2>&1 || true

	_range_start_s=${IMPORT_START_S:-${_oldest_s:-}}
	_range_end_s=${FIRST_VM_S:-$NOW_S}
	if [ -n "$_range_start_s" ] && [ "$_range_start_s" -lt "$_range_end_s" ]; then
		_check_s=$(((_range_start_s + _range_end_s) / 2))
		_check_day=$(date -u -d "@$_check_s" +%Y-%m-%d)
		_series=0
		_waited=0
		while [ "$_waited" -lt 120 ]; do
			_series=$(curl -sf --get "$VM_URL/api/v1/status/tsdb" --data-urlencode "date=$_check_day" --data-urlencode "topN=1" 2>/dev/null |
				sed -n 's/.*"totalSeries":\([0-9]*\).*/\1/p')
			[ "${_series:-0}" -gt 0 ] && break
			_waited=$((_waited + 5))
			sleep 5
		done
		if [ "${_series:-0}" -le 0 ]; then
			err "ERROR: vmctl finished but VictoriaMetrics reports no series for $_check_day, inside the imported range."
			break
		fi
		log "VictoriaMetrics reports ${_series} series for $_check_day (inside the imported range)."
	fi

	MIGRATED=1
	break
done

if [ "$MIGRATED" != 1 ]; then
	err "WARNING: Prometheus -> VictoriaMetrics migration failed. The original data at $PROMETHEUS_DIR was not modified."
	if [ "$IMPORT_STARTED" = 1 ]; then
		err "         Part of the history may already be in VictoriaMetrics; a re-run imports those samples again."
	fi
	exit 1
fi

_archive="$PROMETHEUS_DIR.migrated-$(date +%Y%m%d%H%M%S)"
if $SUDO mv "$PROMETHEUS_DIR" "$_archive"; then
	$SUDO touch "$MARKER" || true
	log "Prometheus data migrated to VictoriaMetrics."
	log "The old Prometheus data has been kept at $_archive; delete it once you have verified VictoriaMetrics: sudo rm -rf $_archive"
else
	err "Metrics imported into VictoriaMetrics, but archiving the old TSDB failed. Run it manually:"
	err "   sudo mv $PROMETHEUS_DIR $_archive && sudo touch $MARKER"
fi
exit 0
