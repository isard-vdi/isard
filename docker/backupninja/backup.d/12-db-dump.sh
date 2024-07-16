#!/bin/sh

when="$BACKUP_DB_WHEN"

rm -f /dbdump/isard-db*.tar.gz
/usr/bin/rethinkdb-dump -c "isard-db:28015" -f "/dbdump/isard-db-$(date +%Y-%m-%d_%H:%M:%S).tar.gz"
