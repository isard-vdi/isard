#!/bin/sh -i
set -e

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

if [ ! -f /certs/chain.pem ]; then
        auto-generate-certs.sh
fi

inotifyd haproxy-reload /certs/chain.pem:c &

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

exec "$@"
