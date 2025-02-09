#!/bin/sh

when = $BACKUP_DISKS_WHEN

# Check if today is Saturday (6)
if [ $(date +%u) -eq 6 ]; then
    # Check if the path exists
    if [ -d "/backup/disks" ]; then
        echo "Compacting Borg repository at /backup/disks..."
        borg compact --progress --cleanup-commits --verbose --threshold 5 "/backup/disks"
    fi
else
    echo "Today is not Saturday. Skipping the /backup/disks backup compacting."
fi
