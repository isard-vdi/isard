#!/usr/bin/env sh

set -e

# Usage: acme-dns-generate-cert.sh <domain> [pem-name] [acme-server]
# Credentials: ACMEDNS_BASE_URL, ACMEDNS_USERNAME, ACMEDNS_SUBDOMAIN in the
# environment; the password on STDIN, never as an argument, or it leaks into
# /proc/<pid>/cmdline and any `ps`.
acme_domain="${1:-}"
acme_pem_name="${2:-chain.pem}"
acme_server="${3:-$ACME_SERVER}"

ACME_HOME="${ACME_HOME:-/etc/acme}"
ACME_CERTS_DIR="${ACME_CERTS_DIR:-/certs}"

# This is done to prevent acme.sh from throwing weird error messages
LOG_LEVEL=""

export LE_WORKING_DIR="$ACME_HOME"

if [ -z "$acme_domain" ]; then
    echo "ERROR: a domain to certify is required" >&2
    exit 1
fi

# One acme.sh run uses one acme-dns account (bounded TXT records) for all
# names; refuse multi-name rather than issue a cert silently missing a name.
if [ "$#" -gt 3 ]; then
    shift 3
    echo "ERROR: dns-01 issuance takes a single name; refusing to ignore: $*" >&2
    exit 1
fi

acmedns_password=""
IFS= read -r acmedns_password || true

missing=""
[ -n "${ACMEDNS_BASE_URL:-}" ] || missing="$missing ACMEDNS_BASE_URL"
[ -n "${ACMEDNS_USERNAME:-}" ] || missing="$missing ACMEDNS_USERNAME"
[ -n "${ACMEDNS_SUBDOMAIN:-}" ] || missing="$missing ACMEDNS_SUBDOMAIN"
[ -n "$acmedns_password" ] || missing="$missing ACMEDNS_PASSWORD (on stdin)"

if [ -n "$missing" ]; then
    echo "ERROR: incomplete acme-dns credentials, missing:$missing" >&2
    exit 1
fi

mkdir -p "$ACME_HOME"

# acme.sh logs the acme-dns request with the password in a header; capture to
# a 0600 file rather than inheriting output, which callers propagate into logs.
acme_log="$ACME_HOME/acme-dns-last-run.log"
: > "$acme_log"
chmod 600 "$acme_log"

# acme.sh state is plain files and not concurrency-safe; serialize on the lock
# the HTTP-01 script also uses.
echo "Generating ACME DNS-01 certificate for $acme_domain"
set +e
(
    flock 9

    ACMEDNS_BASE_URL="$ACMEDNS_BASE_URL" \
        ACMEDNS_USERNAME="$ACMEDNS_USERNAME" \
        ACMEDNS_PASSWORD="$acmedns_password" \
        ACMEDNS_SUBDOMAIN="$ACMEDNS_SUBDOMAIN" \
        acme.sh --issue --dns dns_acmedns --server "$acme_server" -d "$acme_domain" \
        >>"$acme_log" 2>&1
) 9>"$ACME_HOME/.acme-issue.lock"
ACME_EXIT_CODE="$?"
set -e
if [ "$ACME_EXIT_CODE" = 0 ]; then
    echo "ACME DNS-01 certificate generated successfully"
elif [ "$ACME_EXIT_CODE" = 2 ]; then
    # acme.sh exit 2: a valid cert already exists. Still deploy below; it is in
    # the ACME home but not necessarily in place in this container.
    echo "Skipping certificate renewal, there's a valid one already"
else
    echo "ACME DNS-01 certificate generation failed with exit code $ACME_EXIT_CODE" >&2
    echo "acme.sh output kept at $acme_log -- it quotes the acme-dns request, password included, so read it in place rather than pasting it anywhere" >&2
    exit "$ACME_EXIT_CODE"
fi

echo "Deploying certificate to HAProxy..."
set +e
DEPLOY_HAPROXY_HOT_UPDATE=yes \
    DEPLOY_HAPROXY_STATS_SOCKET=/var/run/haproxy.sock \
    DEPLOY_HAPROXY_PEM_NAME="$acme_pem_name" \
    DEPLOY_HAPROXY_PEM_PATH="$ACME_CERTS_DIR" \
    acme.sh --deploy --deploy-hook haproxy -d "$acme_domain"
set -e

if [ ! -f "$ACME_CERTS_DIR/$acme_pem_name" ]; then
    echo "ACME deployment failed: certificate file not created" >&2
    exit 1
fi
