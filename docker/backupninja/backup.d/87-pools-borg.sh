#!/bin/sh

export PATH="/workspace/.venv/bin:$PATH"
export BORG_RELOCATED_REPO_ACCESS_IS_OK=yes
export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes

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

# a manual run has no session NFS mount; nfs_mount.sh is a no-op when already mounted
if [ "$BACKUP_NFS_ENABLED" = "true" ]; then
    if ! "${NFS_MOUNT_CMD:-/usr/local/bin/nfs_mount.sh}"; then
        echo "Fatal: NFS mount failed; not archiving pools"
        exit 1
    fi
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

# borg logs "<path>: open: [Errno 11] ..." for a file held under an NFS delegation
skipped_from() { grep "Resource temporarily unavailable" "$1" | sed 's/: .*//' | sort -u; }

ts=$(date +%Y-%m-%dT%H:%M:%S)
out=$(mktemp)

# $BACKUP_POOLS_CREATE_OPTIONS is deliberately unquoted: word-split like the disks handler
${BACKUP_POOLS_NICE:-ionice -c3 nice -n19} borg create --stats --compression lz4 \
    $BACKUP_POOLS_CREATE_OPTIONS \
    "$REPO::$ts" "$@" >"$out" 2>&1
rc=$?
cat "$out" >>"$LOG_FILE"

# borg: 0 ok, 1 warning (incl. a qcow2 skipped under an NFS lease), >=2 error
if [ "$rc" -ge 2 ]; then
    echo "Fatal: borg create failed for $REPO (exit $rc); skipping prune"
    rm -f "$out"
    exit 1
fi
echo "Info: pools borg create finished (exit $rc, $NDIRS directories)"

# the report parser turns each BACKUP_SKIPPED_FILE warning into skipped_files
skipped=$(skipped_from "$out")
rm -f "$out"
if [ -n "$skipped" ]; then
    echo "Info: retrying $(printf '%s\n' "$skipped" | grep -c .) file(s) borg skipped on the first pass"
    set --
    while IFS= read -r p; do [ -n "$p" ] && set -- "$@" "$p"; done <<EOF
$skipped
EOF
    retry=$(mktemp)
    ${BACKUP_POOLS_NICE:-ionice -c3 nice -n19} borg create --compression lz4 \
        $BACKUP_POOLS_CREATE_OPTIONS \
        "$REPO::$ts-retry" "$@" >"$retry" 2>&1
    rrc=$?
    cat "$retry" >>"$LOG_FILE"
    if [ "$rrc" -ge 2 ]; then
        still="$skipped"
    else
        still=$(skipped_from "$retry")
    fi
    rm -f "$retry"
    # don't leave an empty companion archive behind if the retry recovered nothing
    if [ "$still" = "$skipped" ]; then
        borg delete "$REPO::$ts-retry" >/dev/null 2>&1 || true
    fi
    if [ -n "$still" ]; then
        printf '%s\n' "$still" | while IFS= read -r p; do
            [ -n "$p" ] && echo "Warning: BACKUP_SKIPPED_FILE: $p"
        done
    fi
fi

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
