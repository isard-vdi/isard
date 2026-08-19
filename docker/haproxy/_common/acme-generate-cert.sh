#!/usr/bin/env sh

set -e

acme_domain="$1"
acme_pem_name="${2:-chain.pem}"

# Filesystem locations. Overridable so the test suite
# (docker/haproxy/_common/tests/test_acme_generate_cert.sh) can drive this
# script without touching the container paths, which are the defaults and are
# what production always uses.
ACME_HOME="${ACME_HOME:-/etc/acme}"
ACME_CERTS_DIR="${ACME_CERTS_DIR:-/certs}"

# This is done to prevent acme.sh from throwing weird error messages
LOG_LEVEL=""

export LE_WORKING_DIR="$ACME_HOME"

mkdir -p "$ACME_HOME"

# Generate the certificate.
#
# Serialized on a lock under the ACME home, because two independent callers
# drive this same script against the same acme.sh account: the portal boot path
# (acme-management.sh) for the main domain, and haproxy-sync once per
# per-category branding domain on every DomainSync push. acme.sh keeps its
# account and per-domain state as plain files under the ACME home and is not
# concurrency-safe, so overlapping runs can corrupt that state or spend CA rate
# limit on duplicate orders.
echo "Generating ACME certificate for $acme_domain"
set +e
(
    flock 9
    acme.sh --issue --stateless -d "$acme_domain" --server "$ACME_SERVER"
) 9>"$ACME_HOME/.acme-issue.lock"
ACME_EXIT_CODE="$?"
set -e
if [ "$ACME_EXIT_CODE" = 0 ]; then
    echo "ACME certificate generated successfully"
elif [ "$ACME_EXIT_CODE" = 2 ]; then
    # acme.sh's "a valid certificate already exists". This no-op fast path is
    # what makes repeated startup and reconnect pushes harmless.
    echo "Skipping certificate renewal, there's a valid one already"
else
    echo "ACME certificate generation failed with exit code $ACME_EXIT_CODE"
    exit "$ACME_EXIT_CODE"
fi

# Deploy the certificate to HAProxy
echo "Deploying certificate to HAProxy..."
set +e
DEPLOY_HAPROXY_HOT_UPDATE=yes \
    DEPLOY_HAPROXY_STATS_SOCKET=/var/run/haproxy.sock \
    DEPLOY_HAPROXY_PEM_NAME="$acme_pem_name" \
    DEPLOY_HAPROXY_PEM_PATH="$ACME_CERTS_DIR" \
    acme.sh --deploy --deploy-hook haproxy -d "$acme_domain"
set -e

if [ ! -f "$ACME_CERTS_DIR/$acme_pem_name" ]; then
    echo "ACME deployment failed: certificate file not created"
    exit 1
fi
