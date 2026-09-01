#!/usr/bin/env sh

set -e

acme_domain="$1"
acme_pem_name="${2:-chain.pem}"

# This is done to prevent acme.sh from throwing weird error messages
LOG_LEVEL=""

export LE_WORKING_DIR="/etc/acme"

# ACME_SERVER is defaulted by the entrypoint, which a `docker exec` of this
# script does not inherit; read it in a subshell so an explicit value wins.
haproxy_env="${HAPROXY_ENV_FILE:-/var/run/haproxy-env}"
if [ -z "${ACME_SERVER:-}" ] && [ -r "$haproxy_env" ]; then
    ACME_SERVER="$(. "$haproxy_env"; printf '%s' "$ACME_SERVER")"
    export ACME_SERVER
fi

if [ -z "${ACME_SERVER:-}" ]; then
    echo "ACME_SERVER is empty and '$haproxy_env' does not provide it, refusing to pick a certificate authority at random"
    exit 1
fi

# Generate the certificate
echo "Generating ACME certificate for $acme_domain"
set +e
acme.sh --issue --stateless -d "$acme_domain" --server "$ACME_SERVER"
ACME_EXIT_CODE="$?"
set -e
if [ "$ACME_EXIT_CODE" = 0 ]; then
    echo "ACME certificate generated successfully"
elif [ "$ACME_EXIT_CODE" = 2 ]; then
    echo "Skipping certificate renewal, there's a valid one already"
else
    echo "ACME certificate generation failed with exit code $ACME_EXIT_CODE"
    exit "$ACME_EXIT_CODE"
fi

# Deploy the certificate to HAProxy: the hook writes the PEM and hot-updates it
# over the stats socket.
echo "Deploying certificate to HAProxy..."
set +e
DEPLOY_HAPROXY_HOT_UPDATE=yes \
    DEPLOY_HAPROXY_STATS_SOCKET=/var/run/haproxy.sock \
    DEPLOY_HAPROXY_PEM_NAME="$acme_pem_name" \
    DEPLOY_HAPROXY_PEM_PATH=/certs \
    acme.sh --deploy --deploy-hook haproxy -d "$acme_domain"
DEPLOY_EXIT_CODE="$?"
set -e

# Reported, not fatal: the caller's retry loop runs under `set -e`, and the
# check below passes anyway on a deployment that never ran.
if [ "$DEPLOY_EXIT_CODE" != 0 ]; then
    echo "WARNING: the deployment hook exited $DEPLOY_EXIT_CODE, HAProxy may still be serving the previous certificate for $acme_domain"
fi

if [ ! -f "/certs/$acme_pem_name" ]; then
    echo "ACME deployment failed: certificate file not created"
    exit 1
fi
