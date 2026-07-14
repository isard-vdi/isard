#!/bin/sh

when = $BACKUP_DB_WHEN

# The rethinkdb-* utilities live in the image venv; make them resolvable by
# name regardless of the (cron-scrubbed) PATH the action runs under.
export PATH="/workspace/.venv/bin:$PATH"

rm -f /dbdump/isard-db*.tar.gz
rethinkdb-dump -c "$RETHINKDB_HOST:$RETHINKDB_PORT" -f "/dbdump/isard-db-$(date +%Y-%m-%d_%H:%M:%S).tar.gz"
if [ $? -ne 0 ]; then
    echo "Fatal: Database dump failed for RethinkDB at $RETHINKDB_HOST:$RETHINKDB_PORT" >&2
    exit 1
fi
