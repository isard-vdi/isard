#!/bin/sh

when="$BACKUP_DB_WHEN"

echo "----------- NEW DATABASE BACKUP: $(date +%Y-%m-%d_%H:%M:%S) -----------" >> $$LOG_FILE
