#!/bin/sh

cp /usr/local/etc/alloy/config.alloy /etc/alloy/config.alloy
cp /usr/local/etc/alloy/logs.alloy /etc/alloy/logs.alloy
cp /usr/local/etc/alloy/metrics.alloy /etc/alloy/metrics.alloy

if [ "$PYROSCOPE_EBPF" = "true" ]; then
	cp /usr/local/etc/alloy/profiling.alloy /etc/alloy/profiling.alloy
fi

if [ "$LOG_LEVEL" = "DEBUG" ] || [ "$LOG_LEVEL" = "debug" ]; then
	cp /usr/local/etc/alloy/debug.alloy /etc/alloy/debug.alloy
fi

alloy run \
        --storage.path=/var/lib/alloy/data \
        --server.http.listen-addr=0.0.0.0:12345 \
        --server.http.ui-path-prefix=/debug/grafana-alloy \
        /etc/alloy
