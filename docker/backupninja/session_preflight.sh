#!/bin/sh
# Preflight check: abort the session if the backup target is too full.
# Runs at the start of each backup session so the whole run does not grind
# through hours of work only to blow up mid-way with ENOSPC. A non-zero
# exit is caught by backupninja as FATAL, which forces the eventual report
# to status=CRITICAL even if the per-type borg actions also fail on their
# own.
set -u

LOG_FILE="${LOG_FILE:-/var/log/backupninja.log}"
BACKUP_DIR="${BACKUP_DIR:-/backup}"
MIN_FREE_PERCENT="${BACKUP_MIN_FREE_PERCENT:-10}"

ts() { date '+%Y-%m-%dT%H:%M:%S'; }

if [ ! -d "$BACKUP_DIR" ]; then
    echo "$(ts) Warning: Preflight skipped: $BACKUP_DIR does not exist" >>"$LOG_FILE"
    exit 0
fi

used=$(df -P "$BACKUP_DIR" | awk 'NR==2 {gsub("%","",$5); print $5}')
if [ -z "$used" ]; then
    echo "$(ts) Warning: Preflight skipped: could not read usage for $BACKUP_DIR" >>"$LOG_FILE"
    exit 0
fi

free=$((100 - used))

if [ "$free" -lt "$MIN_FREE_PERCENT" ]; then
    echo "$(ts) Fatal: Preflight aborted: $BACKUP_DIR at ${used}% used (need >= ${MIN_FREE_PERCENT}% free)" >>"$LOG_FILE"
    exit 1
fi

echo "$(ts) Info: Preflight ok: $BACKUP_DIR at ${used}% used, ${free}% free (threshold ${MIN_FREE_PERCENT}%)" >>"$LOG_FILE"
exit 0
