#!/bin/sh

when = $BACKUP_REDIS_WHEN

rm -f /redisdump/dump*.rdb
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --rdb /redisdump/dump-$(date +%Y-%m-%d_%H:%M:%S).rdb
if [ $? -ne 0 ]; then
    echo "Fatal: Redis dump failed - unable to connect to Redis at $REDIS_HOST:$REDIS_PORT" >&2
    exit 1
fi
