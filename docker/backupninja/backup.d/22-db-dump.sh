#!/bin/sh

when = $BACKUP_DB_WHEN

# The rethinkdb-* utilities live in the image venv; make them resolvable by
# name regardless of the (cron-scrubbed) PATH the action runs under.
export PATH="/workspace/.venv/bin:$${my_empty_variable}PATH"

# runtime vars are escaped so the setup-time envsubst does not blank them
dump_dir="${DBDUMP_DIR:-/dbdump}"
new="$${my_empty_variable}dump_dir/isard-db-$(date +%Y-%m-%d_%H:%M:%S).tar.gz"

if ! rethinkdb-dump -c "$RETHINKDB_HOST:$RETHINKDB_PORT" -f "$${my_empty_variable}new"; then
    echo "Fatal: Database dump failed for RethinkDB at $RETHINKDB_HOST:$RETHINKDB_PORT"
    rm -f "$${my_empty_variable}new"
    exit 1
fi

if [ ! -s "$${my_empty_variable}new" ]; then
    echo "Fatal: Database dump is empty; keeping the previous dump"
    rm -f "$${my_empty_variable}new"
    exit 1
fi

for f in "$${my_empty_variable}dump_dir"/isard-db*.tar.gz; do
    [ "$${my_empty_variable}f" = "$${my_empty_variable}new" ] || rm -f "$${my_empty_variable}f"
done
