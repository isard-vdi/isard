#!/usr/bin/env sh

set -e

acme_domain="$1"
acme_pem_name="$2"

# This is done to prevent acme.sh from throwing weird error messages
LOG_LEVEL=""

export LE_WORKING_DIR="/etc/acme"

echo "Removing ACME certificate for $acme_domain"

# Remove from acme.sh tracking (stops future renewals).
acme.sh --remove -d "$acme_domain"

# acme.sh --remove only renames domain.conf and leaves keys, CSR and certs
# behind. Clean up the domain directory so a future --issue starts fresh.
rm -rf "${LE_WORKING_DIR}/${acme_domain}_ecc"

# Remove the PEM file from disk.
rm -f "/certs/$acme_pem_name"

echo "ACME certificate for $acme_domain removed successfully"
