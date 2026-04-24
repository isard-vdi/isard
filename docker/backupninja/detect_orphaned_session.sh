#!/bin/sh
# Detect an orphaned backup session on container startup and report it as
# CRITICAL. Without this, a container that is killed or restarted in the
# middle of a backup leaves a SESSION_START in the log with no matching
# SESSION_END: no report is ever posted, and the rethinkdb `backups` table
# has no record for that day, so the failure is silent.
set -u

LOG_FILE="${LOG_FILE:-/var/log/backupninja.log}"
[ -f "$LOG_FILE" ] || exit 0

last_start=$(grep -n 'BACKUP_SESSION_START:' "$LOG_FILE" | tail -1 | cut -d: -f1)
last_end=$(grep -n 'BACKUP_SESSION_END:' "$LOG_FILE" | tail -1 | cut -d: -f1)

# No sessions in the log at all
[ -n "$last_start" ] || exit 0

# Last SESSION_END comes after the last SESSION_START: previous run closed
# cleanly, nothing to report here.
if [ -n "$last_end" ] && [ "$last_end" -gt "$last_start" ]; then
    exit 0
fi

ts=$(date '+%Y-%m-%dT%H:%M:%S')
{
    echo "$ts Info: >>>> starting action /virtual/aborted-session"
    echo "$ts Fatal: Previous backup session was interrupted before completion (container restart or crash); no SESSION_END was written"
    echo "$ts Fatal: <<<< finished action /virtual/aborted-session: FATAL"
    echo "$ts Info: BACKUP_SESSION_END: automated full backup aborted"
} >>"$LOG_FILE"
sync

echo "Detected orphaned backup session; sending CRITICAL report to API..."
export BACKUP_TYPE="automated"
python3 /usr/local/bin/backup_report.py || echo "Warning: failed to send orphaned-session report"
