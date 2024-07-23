#!/bin/sh

when="$BACKUP_REDIS_WHEN"

rm -f /redisdump/dump*.rdb
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --rdb /redisdump/dump-$(date +%Y-%m-%d_%H:%M:%S).rdb
