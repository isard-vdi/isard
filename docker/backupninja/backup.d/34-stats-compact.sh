#!/bin/sh

when = $BACKUP_STATS_WHEN

# Check if today is Saturday (6)
if [ $(date +%u) -eq 6 ]; then
    # Check if the path exists
    if [ -d "/backup/stats" ]; then
        echo "Compacting Borg repository at /backup/stats..."
        borg compact --progress --cleanup-commits --verbose --threshold 5 "/backup/stats"
    fi
else
    echo "Today is not Saturday. Skipping the /backup/stats backup compacting."
fi
