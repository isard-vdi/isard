#!/bin/sh

# Exit if LETSENCRYPT_DOMAIN is not set
if [ -z "$LETSENCRYPT_DOMAIN" ]; then
    echo "ERROR: LETSENCRYPT_DOMAIN environment variable not set"
    exit 1
fi

CONF_FILE="/etc/letsencrypt/renewal/$LETSENCRYPT_DOMAIN.conf"

if [ -f "$CONF_FILE" ]; then
    # If current certificate was generated with a different authenticator,
    # we need to change it to standalone for the renewal or it won't work.
    sed -i '/^pref_challs/d' "$CONF_FILE"
    sed -i 's/^authenticator.*/authenticator = standalone/' "$CONF_FILE"
    echo "Updated renewal configuration for $LETSENCRYPT_DOMAIN"
else
    echo "No renewal configuration found for $LETSENCRYPT_DOMAIN"
fi

# Attempt certificate renewal
echo "Attempting to renew certificate for $LETSENCRYPT_DOMAIN"
if certbot renew --http-01-port 8080 --cert-name "$LETSENCRYPT_DOMAIN"; then
    echo "Certificate renewal completed successfully"
else
    echo "Certificate renewal failed for $LETSENCRYPT_DOMAIN"
    exit 1
fi
