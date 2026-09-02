#!/usr/bin/env sh

# Nightly acme.sh renewal, appending to its log and rotating it by size: a
# single ">" in the crontab erased the evidence of the night before, and this
# image has no logrotate.

LOG_FILE="${ACME_CRON_LOG:-/var/log/acme-cron.log}"
LOG_MAX_BYTES="${ACME_CRON_LOG_MAX_BYTES:-1048576}"

if [ -f "$LOG_FILE" ]; then
    size=$(wc -c < "$LOG_FILE" | tr -dc '0-9')
    [ -n "$size" ] || size=0
    if [ "$size" -gt "$LOG_MAX_BYTES" ]; then
        mv -f "$LOG_FILE" "$LOG_FILE.1"
    fi
fi

{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] acme.sh --cron starting"
    /usr/share/acme.sh/acme.sh --cron --home "/etc/acme"
    rc=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] acme.sh --cron finished with exit code $rc"
} >> "$LOG_FILE" 2>&1
