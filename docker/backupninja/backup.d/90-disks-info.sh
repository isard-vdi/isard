#!/bin/sh

when="$BACKUP_DISKS_WHEN"

# https://stackoverflow.com/a/61259844
echo "----------- NEW DISKS BACKUP: $(date +%Y-%m-%d_%H:%M:%S) -----------" >> $${my_empty_variable}LOG_FILE
