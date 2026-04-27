#!/bin/sh

when = $BACKUP_CONFIG_WHEN

# Only run if config backup is enabled
if [ "$when" = "disabled" ]; then
    exit 0
fi

# Compact is opt-out via env var. Set BACKUP_COMPACT_ENABLED=false on
# very large repos where compact takes longer than the daily backup
# window and would otherwise block the next day's borg create.
if [ "${BACKUP_COMPACT_ENABLED:-true}" != "true" ]; then
    echo "Compact disabled via BACKUP_COMPACT_ENABLED=false. Skipping /backup/config."
    exit 0
fi

# Check if today is Saturday (6)
if [ $(date +%u) -eq 6 ]; then
    # Check if the path exists
    if [ -d "/backup/config" ]; then
        echo "Compacting Borg repository at /backup/config..."
        borg compact --progress --cleanup-commits --verbose --threshold 5 "/backup/config"
    fi
else
    echo "Today is not Saturday. Skipping the /backup/config backup compacting."
fi
