#!/bin/sh

when = $BACKUP_REDIS_WHEN

# escaped so envsubst never writes the password into the job file; REDISCLI_AUTH keeps it off argv
if [ -n "$${my_empty_variable}REDIS_PASSWORD" ]; then
    export REDISCLI_AUTH="$${my_empty_variable}REDIS_PASSWORD"
fi

dump_dir="${REDISDUMP_DIR:-/redisdump}"
new="$${my_empty_variable}dump_dir/dump-$(date +%Y-%m-%d_%H:%M:%S).rdb"

if ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --rdb "$${my_empty_variable}new"; then
    echo "Fatal: Redis dump failed - unable to reach Redis at $REDIS_HOST:$REDIS_PORT"
    rm -f "$${my_empty_variable}new"
    exit 1
fi

if [ ! -s "$${my_empty_variable}new" ]; then
    echo "Fatal: Redis dump is empty; keeping the previous dump"
    rm -f "$${my_empty_variable}new"
    exit 1
fi

for f in "$${my_empty_variable}dump_dir"/dump*.rdb; do
    [ "$${my_empty_variable}f" = "$${my_empty_variable}new" ] || rm -f "$${my_empty_variable}f"
done
