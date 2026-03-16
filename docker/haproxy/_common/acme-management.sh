#!/usr/bin/env sh

set -e

# This is done to prevent crashes
touch /etc/acme/account-thumbprint

# This is done to prevent acme.sh from throwing weird error messages
LOG_LEVEL=""

if [ -n "$ACME_DOMAIN" ] && [ -n "$ACME_EMAIL" ]; then
    export LE_WORKING_DIR="/etc/acme"

    if [ "$1" = "register" ]; then
        # Create the account
        echo "Registering ACME account '$ACME_EMAIL' for $ACME_SERVER"
        acme.sh --register-account --email "$ACME_EMAIL" --server "$ACME_SERVER" | grep ACCOUNT_THUMBPRINT | awk -F'ACCOUNT_THUMBPRINT=' '{ print $2 }' | xargs > /etc/acme/account-thumbprint

    elif [ "$1" = "generate" ]; then
        # Setup the cron
        echo "Setting up cron"
        echo '0 2 * * * /usr/share/acme.sh/acme.sh --cron --home "/etc/acme" &> /var/log/acme-cron.log' > /etc/crontabs/root
        crond

        # Generate the main domain certificate, retrying until HAProxy serves it
        while true; do
            acme-generate-cert.sh "$ACME_DOMAIN"

            if curl "https://$ACME_DOMAIN:$HTTPS_PORT" &> /dev/null; then
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
