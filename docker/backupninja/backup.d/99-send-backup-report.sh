#!/bin/sh

# This script sends backup reports to the API for automated backups
# It should be the last script to run (hence the 99 prefix)
# The 'when' variable will be dynamically set by run.sh based on enabled backup types

LOG_FILE="/var/log/backupninja.log"

# Add backup session end marker for automated backups
echo "$(date '+%b %d %H:%M:%S') Info: BACKUP_SESSION_END: automated full backup completed by cron" >> "$LOG_FILE"

# Set backup type for automated backups
export BACKUP_TYPE="automated"

# Send backup report to API
echo "$(date '+%b %d %H:%M:%S') Info: Sending automated backup report to API..." >> "$LOG_FILE"
python3 /usr/local/bin/backup_report.py

# Log the result
if [ $? -eq 0 ]; then
    echo "$(date '+%b %d %H:%M:%S') Info: Backup report sent successfully" >> "$LOG_FILE"
else
    echo "$(date '+%b %d %H:%M:%S') Error: Failed to send backup report" >> "$LOG_FILE"
fi
