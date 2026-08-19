#!/usr/bin/env sh

set -e

# Usage: acme-remove-cert.sh <primary-name> <pem-name> [previous-primary-name]
#
# acme.sh indexes a certificate by its FIRST -d, so both the removal and the
# state directory have to name the primary the certificate was issued under.
# The optional third argument names a primary the certificate used to have:
# when the primary changes, acme.sh starts a fresh directory and the old one is
# left behind renewing, forever, a certificate nothing serves.
acme_domain="$1"
acme_pem_name="$2"
acme_previous_domain="${3:-}"

# Filesystem locations. Overridable so the test suite
# (docker/haproxy/_common/tests/test_acme_remove_cert.sh) can drive this script
# without touching the container paths, which are the defaults and are what
# production always uses.
ACME_HOME="${ACME_HOME:-/etc/acme}"
ACME_CERTS_DIR="${ACME_CERTS_DIR:-/certs}"

# This is done to prevent acme.sh from throwing weird error messages
LOG_LEVEL=""

export LE_WORKING_DIR="$ACME_HOME"

# forget_cert <primary-name> — stop renewals and drop the on-disk state.
# acme.sh --remove only renames domain.conf and leaves keys, CSR and certs
# behind, so the directory has to go too or a future --issue starts dirty.
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
