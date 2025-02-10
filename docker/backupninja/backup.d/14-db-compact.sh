#!/bin/sh

when = $BACKUP_DB_WHEN

# Check if today is Saturday (6)
if [ $(date +%u) -eq 6 ]; then
    # Check if the path exists
    if [ -d "/backup/db" ]; then
        echo "Compacting Borg repository at /backup/db..."
        borg compact --progress --cleanup-commits --verbose --threshold 5 /backup/db
    fi
else
    echo "Today is not Saturday. Skipping the /backup/db backup compacting."
fi
