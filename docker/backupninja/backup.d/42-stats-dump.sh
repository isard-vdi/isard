#!/bin/sh

when = $BACKUP_STATS_WHEN

#
# VictoriaMetrics
#
if ! vmbackup \
    -storageDataPath=/opt/isard/stats/victoriametrics \
    -snapshot.createURL=${VICTORIAMETRICS_ADDRESS}/snapshot/create \
    -dst=fs:///opt/isard/stats/victoriametrics-backup
then
    echo "Fatal: vmbackup failed" >&2
    exit 1
fi

#
# Loki
#
curl -sX POST -H "Content-Type: application/json" ${LOKI_ADDRESS}/flush
if [ $? -ne 0 ]; then
    echo "Fatal: Loki flush failed - unable to connect to Loki at $LOKI_ADDRESS" >&2
    exit 1
fi
