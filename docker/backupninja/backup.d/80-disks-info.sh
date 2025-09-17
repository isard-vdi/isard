#!/bin/sh

# https://stackoverflow.com/a/61259844
echo "----------- NEW DISKS BACKUP: $(date +%Y-%m-%d_%H:%M:%S) -----------" >> "$${my_empty_variable}LOG_FILE"

# Log which disk types are enabled for this backup
ENABLED_DISK_TYPES=""
[ -n "$BACKUP_DISKS_TEMPLATES_ENABLED" ] && ENABLED_DISK_TYPES="$ENABLED_DISK_TYPES templates"
[ -n "$BACKUP_DISKS_GROUPS_ENABLED" ] && ENABLED_DISK_TYPES="$ENABLED_DISK_TYPES groups"
[ -n "$BACKUP_DISKS_MEDIA_ENABLED" ] && ENABLED_DISK_TYPES="$ENABLED_DISK_TYPES media"

echo "$(date '+%b %d %H:%M:%S') Info: BACKUP_DISK_TYPES:$ENABLED_DISK_TYPES" >> "$${my_empty_variable}LOG_FILE"
