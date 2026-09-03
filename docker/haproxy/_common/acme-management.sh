#!/usr/bin/env sh

set -e

# This is done to prevent crashes
touch /etc/acme/account-thumbprint

# This is done to prevent acme.sh from throwing weird error messages
LOG_LEVEL=""

if [ -n "$ACME_DOMAIN" ] && [ -n "$ACME_EMAIL" ]; then
    export LE_WORKING_DIR="/etc/acme"

    if [ "$1" = "register" ]; then
        # The thumbprint answers every stateless http-01 challenge and outlives
        # the container, so redirecting into it would truncate it on a failure.
        echo "Registering ACME account '$ACME_EMAIL' for $ACME_SERVER"
        thumbprint="$(acme.sh --register-account --email "$ACME_EMAIL" --server "$ACME_SERVER" | grep ACCOUNT_THUMBPRINT | awk -F'ACCOUNT_THUMBPRINT=' '{ print $2 }' | xargs)"

        if [ -n "$thumbprint" ]; then
            printf '%s\n' "$thumbprint" > /etc/acme/account-thumbprint
        elif [ -s /etc/acme/account-thumbprint ]; then
            echo "WARNING: ACME registration returned no thumbprint, keeping the stored one"
        else
            echo "ERROR: ACME registration returned no thumbprint and none is stored, http-01 validation will fail"
            exit 1
        fi

    elif [ "$1" = "generate" ]; then
        # Setup the cron
        echo "Setting up cron"
        echo '0 2 * * * /usr/local/bin/acme-cron.sh' > /etc/crontabs/root
        crond

        # Generate the main domain certificate, retrying until HAProxy serves it
        while true; do
            acme-generate-cert.sh "$ACME_DOMAIN"

            if curl -k --resolve "$ACME_DOMAIN:$HTTPS_PORT:127.0.0.1" "https://$ACME_DOMAIN:$HTTPS_PORT" &> /dev/null; then
                break
            fi

            echo "Certificate not yet available, retrying in 2 seconds..."
            sleep 2
        done
    else
        echo "Unknown ACME command '$1'"
        exit 1
    fi
fi
