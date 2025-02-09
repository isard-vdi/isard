#!/bin/sh

when = $BACKUP_CONFIG_WHEN

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
