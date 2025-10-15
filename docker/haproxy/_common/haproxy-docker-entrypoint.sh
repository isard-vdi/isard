#!/bin/sh -i
set -e

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting HAProxy container initialization..."

prepare.sh

if [ ! -n "$WEBAPP_HOST" ]; then
        export WEBAPP_HOST='isard-webapp'
fi
if [ ! -n "$RETHINKDB_HOST" ]; then
        export RETHINKDB_HOST='isard-db'
fi
if [ ! -n "$GRAFANA_HOST" ]; then
        export GRAFANA_HOST='isard-grafana'
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Checking for SSL certificate..."
if [ ! -f /certs/chain.pem ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] No SSL certificate found, generating self-signed certificate"
        auto-generate-certs.sh
elif [ ! -s /certs/chain.pem ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] SSL certificate file is empty, regenerating self-signed certificate"
        auto-generate-certs.sh
else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] SSL certificate found ($(stat -c%s /certs/chain.pem) bytes)"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting file monitoring for automatic reloads..."
inotifyd haproxy-reload /certs/chain.pem:c /usr/local/etc/haproxy/lists/black.lst:c /usr/local/etc/haproxy/lists/external/black.lst:c /usr/local/etc/haproxy/lists/white.lst:c &

# first arg is `-f` or `--some-option`
if [ "${1#-}" != "$1" ]; then
        set -- haproxy "$@"
fi

if [ "$1" = 'haproxy' ]; then
        shift # "haproxy"
        # if the user wants "haproxy", let's add a couple useful flags
        #   -W  -- "master-worker mode" (similar to the old "haproxy-systemd-wrapper"; allows for reload via "SIGUSR2")
        #   -db -- disables background mode
        set -- haproxy -W -db "$@"
fi

# Start haproxy-bastion-sync AFTER haproxy starts (in background)
# This ensures the stats socket exists before the microservice tries to connect
if [ "$CFG" = "portal" ]; then
    (
        # Wait a moment for HAProxy to start and create the socket
        sleep 2
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting haproxy-bastion-sync microservice..."
        haproxy-bastion-sync
    ) &
fi

exec "$@"
