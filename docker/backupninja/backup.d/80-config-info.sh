#!/bin/sh

when = $BACKUP_CONFIG_WHEN

# https://stackoverflow.com/a/61259844
echo "----------- NEW CONFIG BACKUP: $(date +%Y-%m-%d_%H:%M:%S) -----------" >> $${my_empty_variable}LOG_FILE
