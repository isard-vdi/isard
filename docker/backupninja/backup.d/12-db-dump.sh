#!/bin/sh

when="$BACKUP_DB_WHEN"

rm -f /dbdump/isard-db*.tar.gz
/usr/bin/rethinkdb-dump -c "$RETHINKDB_HOST:$RETHINKDB_PORT" -f "/dbdump/isard-db-$(date +%Y-%m-%d_%H:%M:%S).tar.gz"
