#!/usr/bin/env sh

set -e

# Usage: acme-remove-cert.sh <primary-name> <pem-name> [previous-primary-name]
# acme.sh indexes a cert by its FIRST -d. The optional previous primary removes
# an old state dir left behind when the primary changed, which else renews forever.
acme_domain="$1"
acme_pem_name="$2"
acme_previous_domain="${3:-}"

# Overridable for the test suite; the defaults are the container paths used in production.
ACME_HOME="${ACME_HOME:-/etc/acme}"
ACME_CERTS_DIR="${ACME_CERTS_DIR:-/certs}"

# This is done to prevent acme.sh from throwing weird error messages
LOG_LEVEL=""

export LE_WORKING_DIR="$ACME_HOME"

# forget_cert <primary-name>: stop renewals and drop on-disk state. acme.sh
# --remove leaves keys/CSR/certs, so the directory must go too or --issue starts dirty.
forget_cert() {
    echo "Removing ACME certificate for $1"
    acme.sh --remove -d "$1"
    rm -rf "${ACME_HOME}/${1}_ecc"
}

forget_cert "$acme_domain"

if [ -n "$acme_previous_domain" ] && [ "$acme_previous_domain" != "$acme_domain" ]; then
    echo "Also removing the previous primary name $acme_previous_domain"
    forget_cert "$acme_previous_domain"
fi

# Remove the PEM file from disk.
rm -f "$ACME_CERTS_DIR/$acme_pem_name"

echo "ACME certificate for $acme_domain removed successfully"
