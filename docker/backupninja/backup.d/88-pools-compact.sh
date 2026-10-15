#!/bin/sh

if [ "${BACKUP_COMPACT_ENABLED:-true}" != "true" ]; then
    echo "Compact disabled via BACKUP_COMPACT_ENABLED=false. Skipping /backup/pools."
    exit 0
fi

if [ "$(date +%u)" -eq 6 ]; then
    borg_compact.sh "/backup/pools"
else
    echo "Today is not Saturday. Skipping the /backup/pools backup compacting."
fi
