#!/bin/sh

export PATH="/workspace/.venv/bin:$PATH"

# backupninja only counts a status that starts at column 0 (^Fatal:/^Warning:)
LOG_FILE="${LOG_FILE:-/var/log/backupninja.log}"
REPO="/backup/pools"
LOCK="/var/lock/backupninja-pools.lock"

# a first pass can last days: skip, never wait for, a run still in progress
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "Warning: previous pools backup still running, skipped"
    exit 0
fi

# never archive or prune a partial set
DIRS_FILE=$(mktemp)
ERR_FILE=$(mktemp)
if ! isardvdi-backup-pool-paths >"$DIRS_FILE" 2>"$ERR_FILE"; then
    echo "Fatal: storage pool path resolution failed; not archiving pools"
    cat "$ERR_FILE" >>"$LOG_FILE"
    rm -f "$DIRS_FILE" "$ERR_FILE"
    exit 1
fi
rm -f "$ERR_FILE"

NDIRS=$(grep -c . "$DIRS_FILE")
if [ "$NDIRS" -eq 0 ]; then
    echo "Info: no category storage-pool disks to back up"
    rm -f "$DIRS_FILE"
    exit 0
fi

borg init -e none "$REPO" >/dev/null 2>&1 || true

set --
while IFS= read -r d; do
    [ -n "$d" ] && set -- "$@" "$d"
done <"$DIRS_FILE"
rm -f "$DIRS_FILE"

# $BACKUP_POOLS_CREATE_OPTIONS is deliberately unquoted: word-split like the disks handler
${BACKUP_POOLS_NICE:-ionice -c3 nice -n19} borg create --stats --compression lz4 \
    $BACKUP_POOLS_CREATE_OPTIONS \
    "$REPO::{now:%Y-%m-%dT%H:%M:%S}" "$@" >>"$LOG_FILE" 2>&1
rc=$?

# borg: 0 ok, 1 warning (files changed while read), >=2 error
if [ "$rc" -ge 2 ]; then
    echo "Fatal: borg create failed for $REPO (exit $rc); skipping prune"
    exit 1
fi
echo "Info: pools borg create finished (exit $rc, $NDIRS directories)"

# an empty prune policy would delete every archive
if [ -z "$BACKUP_POOLS_PRUNE" ]; then
    echo "Warning: BACKUP_POOLS_PRUNE is empty; skipping prune"
    exit 0
fi
borg prune $BACKUP_POOLS_PRUNE "$REPO" >>"$LOG_FILE" 2>&1
prc=$?
if [ "$prc" -ne 0 ]; then
    echo "Warning: borg prune returned $prc for $REPO"
fi
exit 0
