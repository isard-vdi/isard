#!/bin/sh

cp /usr/local/etc/alloy/config.alloy /etc/alloy/config.alloy
cp /usr/local/etc/alloy/logs.alloy /etc/alloy/logs.alloy
cp /usr/local/etc/alloy/metrics.alloy /etc/alloy/metrics.alloy

if [ "$HOST_JOURNAL_LOGS" != "false" ]; then
	cp /usr/local/etc/alloy/journal.alloy /etc/alloy/journal.alloy
else
	rm -f /etc/alloy/journal.alloy
fi

# The probe reaches the container that serves 443 by its name: DOMAIN may resolve to this
# very container (a host /etc/hosts entry pointing it at 127.0.0.1 is inherited).
case "$FLAVOUR" in
	all-in-one | *web*) CERT_PROBE_ADDRESS="isard-portal:${HTTPS_PORT:-443}" ;;
	monitor) CERT_PROBE_ADDRESS="isard-monitor-proxy:${HTTPS_PORT:-443}" ;;
	*) CERT_PROBE_ADDRESS="" ;;
esac
export CERT_PROBE_ADDRESS
if [ -n "$CERT_PROBE_ADDRESS" ]; then
	cp /usr/local/etc/alloy/certificates.alloy /etc/alloy/certificates.alloy
else
	rm -f /etc/alloy/certificates.alloy
fi

if [ "$PYROSCOPE_EBPF" = "true" ]; then
	cp /usr/local/etc/alloy/profiling.alloy /etc/alloy/profiling.alloy
fi

if [ "$LOG_LEVEL" = "DEBUG" ] || [ "$LOG_LEVEL" = "debug" ]; then
	cp /usr/local/etc/alloy/debug.alloy /etc/alloy/debug.alloy
fi

if [ "$FARO_ENABLED" = "true" ]; then
	cp /usr/local/etc/alloy/faro.alloy /etc/alloy/faro.alloy
fi

alloy run \
        --storage.path=/var/lib/alloy/data \
        --server.http.listen-addr=0.0.0.0:12345 \
        --server.http.ui-path-prefix=/debug/grafana-alloy \
        /etc/alloy
