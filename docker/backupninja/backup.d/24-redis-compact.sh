#!/bin/sh

when = $BACKUP_REDIS_WHEN

# Check if today is Saturday (6)
if [ $(date +%u) -eq 6 ]; then
    # Check if the path exists
    if [ -d "/backup/redis" ]; then
        echo "Compacting Borg repository at /backup/redis..."
        borg compact --progress --cleanup-commits --verbose --threshold 5 "/backup/redis"
    fi
else
    echo "Today is not Saturday. Skipping the /backup/redis backup compacting."
fi
