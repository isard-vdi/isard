#!/bin/sh

when = $BACKUP_STATS_WHEN

#
# Prometheus
#
rm -rf /opt/isard/stats/prometheus/snapshots/*

# Create the snapshot
curl -sX POST ${PROMETHEUS_ADDRESS}/api/v1/admin/tsdb/snapshot |
    # Set exit code to 1 if the output doesn't contain '"status":"success"'
    awk -v rc=1 '/"status":"success"/ { rc=0 } 1; END {exit rc}'

#
# Loki
#
curl -sX POST -H "Content-Type: application/json" ${LOKI_ADDRESS}/flush
if [ $? -ne 0 ]; then
    echo "Fatal: Loki flush failed - unable to connect to Loki at $LOKI_ADDRESS" >&2
    exit 1
fi
