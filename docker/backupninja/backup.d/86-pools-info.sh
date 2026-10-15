#!/bin/sh

export PATH="/workspace/.venv/bin:$PATH"
LOG_FILE="${LOG_FILE:-/var/log/backupninja.log}"

echo "----------- NEW POOLS BACKUP: $(date +%Y-%m-%d_%H:%M:%S) -----------" >>"$LOG_FILE"

POOL_DIRS=$(isardvdi-backup-pool-paths --check 2>/dev/null) || POOL_DIRS=""
if [ -n "$POOL_DIRS" ]; then
    echo "$(date '+%b %d %H:%M:%S') Info: BACKUP_POOL_DIRS: $POOL_DIRS" >>"$LOG_FILE"
fi
