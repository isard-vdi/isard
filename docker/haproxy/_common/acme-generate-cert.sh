#!/usr/bin/env sh

set -e

# Usage: acme-generate-cert.sh <primary-name> [pem-name] [acme-server] [acme-email] [extra-name...]
#
# Only the primary name is required, and the first two positions keep the
# meaning they have always had, so the existing callers -- the portal boot path
# and haproxy-sync's per-branding-domain issuance -- are unaffected. Everything
# past the fourth argument is an additional name to put on the same
# certificate; the primary stays first because acme.sh indexes the certificate
# by its first -d.
acme_domain="$1"
acme_pem_name="${2:-chain.pem}"
acme_server="${3:-$ACME_SERVER}"
acme_email="${4:-}"

if [ "$#" -gt 4 ]; then shift 4; else shift "$#"; fi
# "$@" now holds the additional names, if any.

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

# Build the acme.sh argument list, turning each name into its own -d pair.
# Every name stays a separate argv element: joining them into one string would
# make a name containing whitespace an argument-injection vector into acme.sh.
extra_names=$#
set -- "$@" --issue --stateless --server "$acme_server" -d "$acme_domain"
while [ "$extra_names" -gt 0 ]; do
    name="$1"
    shift
    set -- "$@" -d "$name"
    extra_names=$((extra_names - 1))
done

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

    # Register the account when one was requested and we do not have its
    # thumbprint yet. HAProxy answers the stateless HTTP-01 challenge from that
    # thumbprint, so an account we cannot name is an account whose challenges
    # nobody can satisfy. Guarded on the stored value rather than run every
    # time, to keep issuance from spending an ACME round trip per call.
    if [ -n "$acme_email" ] && [ ! -s "$ACME_HOME/account-thumbprint" ]; then
        echo "Registering ACME account '$acme_email' for $acme_server"
        acme_thumbprint=$(acme.sh --register-account --email "$acme_email" --server "$acme_server" 2>/dev/null \
            | grep ACCOUNT_THUMBPRINT \
            | awk -F'ACCOUNT_THUMBPRINT=' '{ print $2 }' | xargs)
        if [ -n "$acme_thumbprint" ]; then
            printf '%s\n' "$acme_thumbprint" > "$ACME_HOME/account-thumbprint"
        else
            echo "WARNING: could not obtain the ACME account thumbprint for $acme_email"
        fi
    fi

    acme.sh "$@"
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

# Deploy the certificate to HAProxy. Keyed on the primary name: acme.sh looks
# the certificate up by the name it was indexed under, not by the whole set.
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
