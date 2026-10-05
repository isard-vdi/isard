#!/bin/sh

when = $BACKUP_DB_WHEN

# Only run if db backup is enabled
if [ "$when" = "disabled" ]; then
    exit 0
fi

# Compact is opt-out via env var. Set BACKUP_COMPACT_ENABLED=false on
# very large repos where compact takes longer than the daily backup
# window and would otherwise block the next day's borg create.
if [ "${BACKUP_COMPACT_ENABLED:-true}" != "true" ]; then
    echo "Compact disabled via BACKUP_COMPACT_ENABLED=false. Skipping /backup/db."
    exit 0
fi

# Check if today is Saturday (6)
if [ $(date +%u) -eq 6 ]; then
    borg_compact.sh "/backup/db"
else
    echo "Today is not Saturday. Skipping the /backup/db backup compacting."
fi
