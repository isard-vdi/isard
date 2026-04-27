#!/bin/bash

set -u

LOG_FILE="${LOG_FILE:-/var/log/backupninja.log}"

# If the caller set BACKUP_TYPE, honour it (e.g. manual runs). Cron-driven
# invocations inherit "automated" from the generated 90-session-report-*.sh.
BACKUP_TYPE_FOR_SESSION="${BACKUP_TYPE:-automated}"

# Session end marker. The parser reads the timestamp, not the text, so the
# trailing description is informational only. We still include the type for
# readability when tailing the log.
printf '%s Info: BACKUP_SESSION_END: %s backup completed\n' \
    "$(date '+%Y-%m-%dT%H:%M:%S')" \
    "$BACKUP_TYPE_FOR_SESSION" >>"$LOG_FILE"

sync

# Parser consults BACKUP_TYPE as a fallback. Export the caller's value; do
# not overwrite it to "automated".
export BACKUP_TYPE="$BACKUP_TYPE_FOR_SESSION"

python3 /usr/local/bin/backup_report.py
