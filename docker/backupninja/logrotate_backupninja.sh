#!/bin/sh
# copytruncate under a running borg can drop the START/END markers the report parser needs
if pgrep -x borg >/dev/null 2>&1; then
    exit 0
fi

mkdir -p /var/lib/logrotate
exec logrotate -s /var/lib/logrotate/backupninja.status /usr/local/etc/logrotate-backupninja.conf
