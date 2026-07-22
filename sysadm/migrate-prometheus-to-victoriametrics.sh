#!/bin/bash
#
# IsardVDI - On-demand Prometheus -> VictoriaMetrics metrics migration
#
# Imports the historic Prometheus TSDB into VictoriaMetrics. This used to run
# in-band inside build.sh, but on a monitor with real retention (e.g. months of
# data across several remote hosts) the import takes HOURS and needs free disk
# for the old TSDB, the snapshot and the imported data at once -- unsafe inside
# the build/upgrade window. It is therefore a separate admin action, run
# ON DEMAND, outside the window, ideally in the background.
#
# What it does (idempotent -- a marker guards against re-running):
#   1. Snapshots the existing Prometheus TSDB with a throwaway Prometheus.
#   2. Stops the live isard-victoriametrics, imports the snapshot into its data
#      dir with vmctl, then restarts it.
#   3. Archives the old Prometheus data and drops a marker.
#
# NOTE: metrics collection into VictoriaMetrics is paused for the duration of the
# import (step 2). New metrics gathered meanwhile are not lost -- grafana-alloy /
# remote-write buffer and resend -- but plan for the downtime anyway.
#
# Usage:
#   sudo bash sysadm/migrate-prometheus-to-victoriametrics.sh            # migrate
#   sudo bash sysadm/migrate-prometheus-to-victoriametrics.sh --force    # skip the free-space check
#   sudo bash sysadm/migrate-prometheus-to-victoriametrics.sh --help
#
# Background (recommended -- it can run for hours):
#   sudo nohup bash sysadm/migrate-prometheus-to-victoriametrics.sh \
#       >/opt/isard/migrate-prometheus-to-victoriametrics.log 2>&1 &
#
# Environment overrides:
#   ISARD_DIR   install dir holding docker-compose-parts/ (default: autodetected, else /opt/isard)
#   STATS_DIR   metrics data dir (default: $ISARD_DIR/stats)
#
set -eu

FORCE=0
for arg in "$@"; do
	case "$arg" in
	--force) FORCE=1 ;;
	-h | --help)
		sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'
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
PROMETHEUS_IMAGE="prom/prometheus:v3.5.2"
PROMETHEUS_CONTAINER="isard-prometheus-migrate"
VICTORIAMETRICS_CONTAINER="isard-victoriametrics-migrate"

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
VICTORIAMETRICS_IMAGE="victoriametrics/victoria-metrics:$VICTORIAMETRICS_TAG"
VMCTL_IMAGE="victoriametrics/vmctl:$VICTORIAMETRICS_TAG"

# --- Free-space check --------------------------------------------------------
# The snapshot is hard-linked (cheap), but the imported VictoriaMetrics data
# grows alongside the still-present Prometheus TSDB. Require, conservatively, at
# least as much free space on the stats filesystem as the Prometheus data size.
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
VM_WAS_RUNNING=0

cleanup() {
	docker stop "$VICTORIAMETRICS_CONTAINER" >/dev/null 2>&1 || true
	docker rm -f "$PROMETHEUS_CONTAINER" "$VICTORIAMETRICS_CONTAINER" >/dev/null 2>&1 || true
	# Bring the live VictoriaMetrics back if we stopped it.
	if [ "$VM_WAS_RUNNING" = 1 ]; then
		docker start isard-victoriametrics >/dev/null 2>&1 || true
	fi
}
trap cleanup EXIT INT TERM

log "Migrating Prometheus metrics at $PROMETHEUS_DIR to VictoriaMetrics ($VICTORIAMETRICS_TAG)..."

docker rm -f "$PROMETHEUS_CONTAINER" "$VICTORIAMETRICS_CONTAINER" >/dev/null 2>&1 || true
docker stop isard-prometheus >/dev/null 2>&1 || true

while :; do
	log "Starting a temporary Prometheus to snapshot the old TSDB..."
	if ! docker run -d --name "$PROMETHEUS_CONTAINER" --user root -v "$PROMETHEUS_DIR:/prometheus" "$PROMETHEUS_IMAGE" \
		--config.file=/etc/prometheus/prometheus.yml \
		--storage.tsdb.path=/prometheus --web.enable-admin-api >/dev/null; then
		err "ERROR: could not start the temporary Prometheus."
		break
	fi

	_prometheus_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$PROMETHEUS_CONTAINER" 2>/dev/null || true)
	if [ -z "$_prometheus_ip" ]; then
		err "ERROR: could not resolve the temporary Prometheus IP."
		break
	fi

	log "Creating a Prometheus snapshot (waiting for it to be ready)..."
	_snapshot_url="http://$_prometheus_ip:9090/api/v1/admin/tsdb/snapshot"
	_snapshot=""
	_waited=0
	while [ "$_waited" -lt 60 ]; do
		_snapshot=$(curl -sf -X POST "$_snapshot_url" 2>/dev/null | sed -n 's/.*"name":"\([^"]*\)".*/\1/p')
		[ -n "$_snapshot" ] && break
		_waited=$((_waited + 1))
		sleep 1
	done
	if [ -z "$_snapshot" ]; then
		err "ERROR: the temporary Prometheus did not return a snapshot after 60s. Its logs:"
		docker logs --tail 20 "$PROMETHEUS_CONTAINER" 2>&1 | sed 's/^/    /' >&2 || true
		break
	fi
	log "Snapshot created: $_snapshot"

	# Stop the live VictoriaMetrics so the temporary one can own the data dir.
	if [ -n "$(docker ps -q -f name='^isard-victoriametrics$' 2>/dev/null)" ]; then
		VM_WAS_RUNNING=1
		log "Stopping the live isard-victoriametrics for the import..."
		docker stop isard-victoriametrics >/dev/null 2>&1 || true
	fi

	log "Starting a temporary VictoriaMetrics..."
	if ! docker run -d --name "$VICTORIAMETRICS_CONTAINER" --user root -v "$VICTORIAMETRICS_DIR:/victoria-metrics-data" "$VICTORIAMETRICS_IMAGE" \
		-storageDataPath=/victoria-metrics-data >/dev/null; then
		err "ERROR: could not start the temporary VictoriaMetrics."
		break
	fi

	_victoriametrics_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$VICTORIAMETRICS_CONTAINER" 2>/dev/null || true)
	if [ -z "$_victoriametrics_ip" ]; then
		err "ERROR: could not resolve the temporary VictoriaMetrics IP."
		break
	fi

	log "Waiting for VictoriaMetrics to be ready..."
	_ready=0
	_waited=0
	while [ "$_waited" -lt 60 ]; do
		if curl -sf "http://$_victoriametrics_ip:8428/health" >/dev/null 2>&1; then
			_ready=1
			break
		fi
		_waited=$((_waited + 1))
		sleep 1
	done
	if [ "$_ready" != 1 ]; then
		err "ERROR: the temporary VictoriaMetrics was not healthy after 60s."
		break
	fi

	log "Importing the snapshot into VictoriaMetrics with vmctl (this can take a long time)..."
	if ! docker run --rm -t --network host --user root \
		-v "$PROMETHEUS_DIR/snapshots/$_snapshot:/snapshot" "$VMCTL_IMAGE" \
		prometheus -s --prom-snapshot=/snapshot --vm-addr="http://$_victoriametrics_ip:8428"; then
		err "ERROR: vmctl import failed."
		break
	fi

	MIGRATED=1
	break
done

# cleanup() (trap) stops/removes the temp containers and restarts the live VM.

if [ "$MIGRATED" != 1 ]; then
	err "WARNING: Prometheus -> VictoriaMetrics migration failed; old data left intact at $PROMETHEUS_DIR."
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
