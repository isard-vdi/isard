#!/bin/bash

LOG_FILE="/var/log/backupninja.log"

# Determine backup type based on context (default to automated for scheduled runs)
BACKUP_TYPE_FOR_SESSION="${BACKUP_TYPE:-automated}"

# Add backup session end marker BEFORE calling the parser
echo "$(date '+%b %d %H:%M:%S') Info: BACKUP_SESSION_END: $BACKUP_TYPE_FOR_SESSION full backup completed" >> "$LOG_FILE"

# Force flush to disk
sync

# Set backup type for the parser
export BACKUP_TYPE="automated"

# Execute the backup report script
python3 /usr/local/bin/backup_report.py