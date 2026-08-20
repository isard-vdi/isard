#!/usr/bin/env sh

set -e

# Usage: acme-dns-generate-cert.sh <domain> [pem-name] [acme-server]
#
# Issues with the DNS-01 challenge through an acme-dns account, for names that
# cannot use HTTP-01 because they do not point at this deployment.
#
# The four acme-dns credentials arrive out of band, not as arguments:
#
#   ACMEDNS_BASE_URL, ACMEDNS_USERNAME and ACMEDNS_SUBDOMAIN in the environment
#   the password on STDIN, one line
#
# The password is split off from the rest on purpose. Passing it as an argument
# puts it in /proc/<pid>/cmdline for the length of the issuance, where anything
# else in this container can read it and where any `ps` an operator runs while
# debugging will print it -- which is precisely when they are most likely to be
# running one. It is placed in acme.sh's environment because the dns_acmedns
# plugin offers no other way in.
#
# acme.sh then writes the password into its own per-certificate config file, in
# the clear, because it needs it to renew unattended. That is inherent to
# unattended DNS-01 renewal and is not something this script can avoid; what it
# can avoid is the wider exposure of the process table.
acme_domain="${1:-}"
acme_pem_name="${2:-chain.pem}"
acme_server="${3:-$ACME_SERVER}"

# Filesystem locations. Overridable so the test suite
# (docker/haproxy/_common/tests/test_acme_dns_generate_cert.sh) can drive this
# script without touching the container paths, which are the defaults and are
# what production always uses.
ACME_HOME="${ACME_HOME:-/etc/acme}"
ACME_CERTS_DIR="${ACME_CERTS_DIR:-/certs}"

# This is done to prevent acme.sh from throwing weird error messages
LOG_LEVEL=""

export LE_WORKING_DIR="$ACME_HOME"

if [ -z "$acme_domain" ]; then
    echo "ERROR: a domain to certify is required" >&2
    exit 1
fi

# One acme.sh invocation uses ONE acme-dns account for every name on the
# certificate, and an account holds a bounded number of TXT records, so a
# multi-name certificate over acme-dns is a different problem from a
# multi-name certificate over HTTP-01 and needs its own design. Refusing is
# the safe half of not having one: issuing a certificate silently missing a
# name fails TLS in a browser, nowhere near anything that mentions
# certificates.
if [ "$#" -gt 3 ]; then
    shift 3
    echo "ERROR: dns-01 issuance takes a single name; refusing to ignore: $*" >&2
    exit 1
fi

# Read the password from stdin rather than from an argument. A caller that
# sends nothing leaves it empty, which is caught below with the rest.
acmedns_password=""
IFS= read -r acmedns_password || true

missing=""
[ -n "${ACMEDNS_BASE_URL:-}" ] || missing="$missing ACMEDNS_BASE_URL"
[ -n "${ACMEDNS_USERNAME:-}" ] || missing="$missing ACMEDNS_USERNAME"
[ -n "${ACMEDNS_SUBDOMAIN:-}" ] || missing="$missing ACMEDNS_SUBDOMAIN"
[ -n "$acmedns_password" ] || missing="$missing ACMEDNS_PASSWORD (on stdin)"

# Checked here rather than left to acme.sh, which fails much later with a
# message about DNS resolution. That sends the operator to look at their zone
# when what is actually wrong is the configuration they just saved.
if [ -n "$missing" ]; then
    echo "ERROR: incomplete acme-dns credentials, missing:$missing" >&2
    exit 1
fi

mkdir -p "$ACME_HOME"

# Generate the certificate.
#
# Serialized on the same lock the HTTP-01 script uses, and that shared lock is
# the point: a deployment can have one domain on each challenge, and both
# scripts drive the same acme.sh account and the same state directory. acme.sh
# keeps that state as plain files and is not concurrency-safe, so overlapping
# runs can corrupt it or spend certificate-authority rate limit on duplicate
# orders.
echo "Generating ACME DNS-01 certificate for $acme_domain"
set +e
(
    flock 9

    ACMEDNS_BASE_URL="$ACMEDNS_BASE_URL" \
        ACMEDNS_USERNAME="$ACMEDNS_USERNAME" \
        ACMEDNS_PASSWORD="$acmedns_password" \
        ACMEDNS_SUBDOMAIN="$ACMEDNS_SUBDOMAIN" \
        acme.sh --issue --dns dns_acmedns --server "$acme_server" -d "$acme_domain"
) 9>"$ACME_HOME/.acme-issue.lock"
ACME_EXIT_CODE="$?"
set -e
if [ "$ACME_EXIT_CODE" = 0 ]; then
    echo "ACME DNS-01 certificate generated successfully"
elif [ "$ACME_EXIT_CODE" = 2 ]; then
    # acme.sh's "a valid certificate already exists". This no-op fast path is
    # what makes repeated startup and reconnect pushes harmless. It still
    # deploys below: the certificate exists in the ACME home, which does not
    # mean this container has it in place yet.
    echo "Skipping certificate renewal, there's a valid one already"
else
    # Deliberately only the code. acme.sh's output on a DNS-01 failure quotes
    # the request it made, and the password is in it.
    echo "ACME DNS-01 certificate generation failed with exit code $ACME_EXIT_CODE" >&2
    exit "$ACME_EXIT_CODE"
fi

# Deploy the certificate to HAProxy.
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
