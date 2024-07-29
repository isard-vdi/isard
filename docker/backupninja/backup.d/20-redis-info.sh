#!/bin/sh

when = $BACKUP_REDIS_WHEN

# https://stackoverflow.com/a/61259844
echo "----------- NEW REDIS BACKUP: $(date +%Y-%m-%d_%H:%M:%S) -----------" >> $${my_empty_variable}LOG_FILE
