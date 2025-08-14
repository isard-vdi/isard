#!/bin/sh

# Exit if LETSENCRYPT_DOMAIN is not set
if [ -z "$LETSENCRYPT_DOMAIN" ]; then
    echo "ERROR: LETSENCRYPT_DOMAIN environment variable not set"
    exit 1
fi

# Exit if LETSENCRYPT_EMAIL is not set
if [ -z "$LETSENCRYPT_EMAIL" ]; then
    echo "ERROR: LETSENCRYPT_EMAIL environment variable not set"
    exit 1
fi

CONF_FILE="/etc/letsencrypt/renewal/$LETSENCRYPT_DOMAIN.conf"

if [ -f "$CONF_FILE" ]; then
    # If current certificate was generated with a different authenticator,
    # we need to change it to standalone for the renewal or it won't work.
    sed -i '/^pref_challs/d' "$CONF_FILE"
    sed -i 's/^authenticator.*/authenticator = standalone/' "$CONF_FILE"

    # Update server URL to current Let's Encrypt API v2 if it's still using v1
    sed -i 's|acme-v01\.api\.letsencrypt\.org/directory|acme-v02.api.letsencrypt.org/directory|g' "$CONF_FILE"

    echo "Updated renewal configuration for $LETSENCRYPT_DOMAIN"
else
    echo "No renewal configuration found for $LETSENCRYPT_DOMAIN"
fi

# Attempt certificate renewal
echo "Attempting to renew certificate for $LETSENCRYPT_DOMAIN"
if certbot renew --http-01-port 8080 --cert-name "$LETSENCRYPT_DOMAIN"; then
    echo "Certificate renewal completed successfully"
else
    echo "Certificate renewal failed, attempting to re-issue certificate"

    # Check if the failure is due to missing account
    if certbot renew --http-01-port 8080 --cert-name "$LETSENCRYPT_DOMAIN" 2>&1 | grep -q "Account.*does not exist"; then
        echo "Account missing, re-issuing certificate with new account"

        # Remove the old configuration to force a fresh start
        if [ -f "$CONF_FILE" ]; then
            echo "Backing up old renewal configuration"
            mv "$CONF_FILE" "${CONF_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        fi

        # Re-issue the certificate with a new account
        if certbot certonly --standalone -d "$LETSENCRYPT_DOMAIN" -m "$LETSENCRYPT_EMAIL" -n --agree-tos --http-01-port 8080 --force-renewal; then
            echo "Certificate re-issued successfully with new account"

            # Execute the deployment hook manually
            if [ -f /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh ]; then
                RENEWED_LINEAGE="/etc/letsencrypt/live/$(echo "$LETSENCRYPT_DOMAIN" | tr '[:upper:]' '[:lower:]')" /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh
            else
                echo "WARNING: Deployment hook not found, certificate may not be properly deployed"
            fi
        else
            echo "ERROR: Failed to re-issue certificate"
            exit 1
        fi
    else
        echo "ERROR: Certificate renewal failed for unknown reason"
        exit 1
    fi
fi
