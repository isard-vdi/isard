#!/bin/sh

export PATH="/workspace/.venv/bin:$PATH"

# backupninja only counts a status that starts at column 0 (^Warning:)
COUNT=$(isardvdi-backup-pool-paths --check 2>/dev/null)
if [ -z "$COUNT" ]; then
    echo "Warning: could not check storage pools; set BACKUP_POOLS_ENABLED=true to back them up"
elif [ "$COUNT" -gt 0 ]; then
    echo "Warning: $COUNT storage pool directories hold disks that are not backed up; set BACKUP_POOLS_ENABLED=true"
fi
exit 0
