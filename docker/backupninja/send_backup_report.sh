#!/bin/bash

# Set backup type to automated when called from post-action (automated backups)
export BACKUP_TYPE="automated"

# Execute the backup report script
python3 /usr/local/bin/backup_report.py