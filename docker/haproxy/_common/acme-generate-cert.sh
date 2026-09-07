#!/usr/bin/env sh

set -e

# Usage: acme-generate-cert.sh <primary-name> [pem-name] [acme-server] [acme-email] [extra-name...]
# Names past the fourth arg go on the same cert; the primary stays first, acme.sh indexes by first -d.
acme_domain="$1"
acme_pem_name="${2:-chain.pem}"
acme_server="${3:-$ACME_SERVER}"
acme_email="${4:-}"

if [ "$#" -gt 4 ]; then shift 4; else shift "$#"; fi

# Overridable for the test suite; the defaults are the container paths used in production.
ACME_HOME="${ACME_HOME:-/etc/acme}"
ACME_CERTS_DIR="${ACME_CERTS_DIR:-/certs}"

# This is done to prevent acme.sh from throwing weird error messages
LOG_LEVEL=""

export LE_WORKING_DIR="$ACME_HOME"

mkdir -p "$ACME_HOME"

# A `docker exec` of this script does not inherit the entrypoint's ACME_SERVER,
# so read it from the saved env; refuse an empty one rather than let acme.sh pick a CA.
haproxy_env="${HAPROXY_ENV_FILE:-/var/run/haproxy-env}"
if [ -z "$acme_server" ] && [ -r "$haproxy_env" ]; then
    acme_server="$(. "$haproxy_env"; printf '%s' "$ACME_SERVER")"
fi

if [ -z "$acme_server" ]; then
    echo "ACME_SERVER is empty and '$haproxy_env' does not provide it, refusing to pick a certificate authority at random"
    exit 1
fi

# Turn each name into its own -d pair. Each name stays a separate argv element:
# joining them would make a name with whitespace an argument-injection vector into acme.sh.
extra_names=$#
set -- "$@" --issue --stateless --server "$acme_server" -d "$acme_domain"
while [ "$extra_names" -gt 0 ]; do
    name="$1"
    shift
    set -- "$@" -d "$name"
    extra_names=$((extra_names - 1))
done

# Serialized on a lock under the ACME home: two callers (portal boot and
# haproxy-sync per branding domain) drive the same acme.sh state, which is not
# concurrency-safe.
echo "Generating ACME certificate for $acme_domain"
set +e
(
    flock 9

    # Register the account when requested and not yet stored. Guarded on the
    # stored thumbprint to avoid an ACME round trip per call.
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
    # acme.sh's "valid cert already exists": the no-op fast path that makes repeated pushes harmless.
    echo "Skipping certificate renewal, there's a valid one already"
else
    echo "ACME certificate generation failed with exit code $ACME_EXIT_CODE"
    exit "$ACME_EXIT_CODE"
fi

# Deploy to HAProxy, keyed on the primary name acme.sh indexed the cert under.
echo "Deploying certificate to HAProxy..."
set +e
DEPLOY_HAPROXY_HOT_UPDATE=yes \
    DEPLOY_HAPROXY_STATS_SOCKET=/var/run/haproxy.sock \
    DEPLOY_HAPROXY_PEM_NAME="$acme_pem_name" \
    DEPLOY_HAPROXY_PEM_PATH="$ACME_CERTS_DIR" \
    acme.sh --deploy --deploy-hook haproxy -d "$acme_domain"
DEPLOY_EXIT_CODE="$?"
set -e

# Reported, not fatal: the caller's retry loop runs under set -e.
if [ "$DEPLOY_EXIT_CODE" != 0 ]; then
    echo "WARNING: the deployment hook exited $DEPLOY_EXIT_CODE, HAProxy may still be serving the previous certificate for $acme_domain"
fi

if [ ! -f "$ACME_CERTS_DIR/$acme_pem_name" ]; then
    echo "ACME deployment failed: certificate file not created"
    exit 1
fi
