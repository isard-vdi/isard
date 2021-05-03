#!/bin/sh
set -e

prepare.sh

if [ ! -f /certs/chain.pem ]; then
        auto-generate-certs.sh
fi

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
