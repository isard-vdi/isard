#!/bin/sh -i
set -e

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting HAProxy container initialization..."

# Set default variables
if [ -n "$VIDEO_DOMAIN" ]; then
        export DOMAIN="$VIDEO_DOMAIN"
fi
if [ ! -n "$HTTP_PORT" ]; then
        export HTTP_PORT=80
fi
if [ ! -n "$HTTPS_PORT" ]; then
        export HTTPS_PORT=443
fi
if [ -n "$VIEWER_SPICE" ]; then
        export HTTP_PORT="$VIEWER_SPICE"
fi
if [ -n "$VIEWER_BROWSER" ]; then
        export HTTPS_PORT="$VIEWER_BROWSER"
fi
if [ ! -n "$WEBAPP_HOST" ]; then
        export WEBAPP_HOST='isard-webapp'
fi
if [ ! -n "$RETHINKDB_HOST" ]; then
        export RETHINKDB_HOST='isard-db'
fi
if [ ! -n "$GRAFANA_HOST" ]; then
        export GRAFANA_HOST='isard-grafana'
fi
# This is kept for backwards compatibility
if [ -n "$LETSENCRYPT_EMAIL" ]; then
        export ACME_EMAIL="$LETSENCRYPT_EMAIL"
fi
if [ ! -n "$ACME_SERVER" ]; then
        export ACME_SERVER="letsencrypt"
fi

# Prepare ACME variables
if [ -n "$ACME_EMAIL" ]; then
    export ACME_DOMAIN="$DOMAIN"
    if [ -n "$VIDEO_DOMAIN" ]; then
        export ACME_DOMAIN="$VIDEO_DOMAIN"
        echo "Using VIDEO_DOMAIN: $VIDEO_DOMAIN for ACME certificate"
    else
        echo "Using DOMAIN: $DOMAIN for ACME certificate"
    fi
fi

# Decide which parts will be active
FLAVOUR="$(echo -n "$FLAVOUR" | tr '+' ' ')"

if [ "$FLAVOUR" = "all-in-one" ]
then
  FLAVOUR="web video monitor"
fi


# Prepare HAProxy configuration
prepare.sh

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

# Start file monitoring for HAProxy reloads
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting file monitoring for automatic reloads..."
inotifyd haproxy-reload /usr/local/etc/haproxy/lists/black.lst:c /usr/local/etc/haproxy/lists/external/black.lst:c /usr/local/etc/haproxy/lists/white.lst:c &


# Load the ACME generated thumbprint
export ACME_ACCOUNT_THUMBPRINT="$(cat /etc/acme/account-thumbprint)"

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

# Start ACME certificate management AFTER haproxy starts (in background)
# This ensures the admin socket exists before the program tries to connect
# This also ensures the frontend is listening
if [ -n "$ACME_EMAIL" ]; then
    (
        # Wait a moment for HAProxy to start and create the socket
        sleep 3
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting ACME certificate management..."
        if ! acme-management.sh generate; then
            echo "WARNING: ACME certificate acquisition failed for $ACME_DOMAIN"
        fi
    ) &
fi

for part in $FLAVOUR; do
  if [ "$part" = "web" ]; then
    # Start haproxy-bastion-sync AFTER haproxy starts (in background)
    # This ensures the stats socket exists before the microservice tries to connect
    (
        # Wait a moment for HAProxy to start and create the socket
        sleep 2
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting haproxy-bastion-sync microservice..."
        haproxy-bastion-sync
    ) &
  fi
done

exec "$@"
