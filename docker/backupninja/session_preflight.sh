#!/bin/sh
# backupninja counts only ^Fatal:/^Warning: at column 0 of stdout, not the exit code
set -u

# /backup is the container mount; BACKUP_DIR is the host path, absent in here
BACKUP_TARGET="${BACKUP_TARGET:-/backup}"
MIN_FREE_PERCENT="${BACKUP_MIN_FREE_PERCENT:-10}"

ts() { date '+%Y-%m-%dT%H:%M:%S'; }

if [ ! -d "$BACKUP_TARGET" ]; then
    echo "Fatal: Preflight: backup target $BACKUP_TARGET is missing at $(ts); the session has no destination"
    exit 1
fi

used=$(df -P "$BACKUP_TARGET" | awk 'NR==2 {gsub("%","",$5); print $5}')
if [ -z "$used" ]; then
    echo "Warning: Preflight: could not read usage for $BACKUP_TARGET at $(ts); proceeding"
    exit 0
fi

free=$((100 - used))

if [ "$free" -lt "$MIN_FREE_PERCENT" ]; then
    echo "Fatal: Preflight aborted at $(ts): $BACKUP_TARGET at ${used}% used (need >= ${MIN_FREE_PERCENT}% free)"
    exit 1
fi

echo "Info: Preflight ok at $(ts): $BACKUP_TARGET at ${used}% used, ${free}% free (threshold ${MIN_FREE_PERCENT}%)"
exit 0
