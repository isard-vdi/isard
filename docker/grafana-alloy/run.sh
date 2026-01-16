#!/bin/sh

cp /usr/local/etc/alloy/config.alloy /etc/alloy/config.alloy
cp /usr/local/etc/alloy/logs.alloy /etc/alloy/logs.alloy
cp /usr/local/etc/alloy/metrics.alloy /etc/alloy/metrics.alloy

if [ -z "$FLAVOUR" ] || [ "$FLAVOUR" = "all-in-one" ] || [ "$FLAVOUR" = "web" ]; then
	cp /usr/local/etc/alloy/metrics-web.alloy etc/alloy/metrics-web.alloy

elif [ "$FLAVOUR" = "hypervisor" ] || [ "$FLAVOUR" = "video-standalone" ]; then
	cp /usr/local/etc/alloy/metrics-video.alloy etc/alloy/metrics-video.alloy

elif [ "$FLAVOUR" = "monitor" ]; then
	cp /usr/local/etc/alloy/metrics-monitor.alloy etc/alloy/metrics-monitor.alloy
fi

if [ "$PYROSCOPE_EBPF" = "true" ]; then
	cp /usr/local/etc/alloy/profiling.alloy /etc/alloy/profiling.alloy
fi

alloy run \
        --storage.path=/var/lib/alloy/data \
        --server.http.listen-addr=0.0.0.0:12345 \
        --server.http.ui-path-prefix=/debug/grafana-alloy \
        /etc/alloy
