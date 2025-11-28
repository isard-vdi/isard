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

        # Generate the certificate
        echo "Generating ACME certificate for $ACME_DOMAIN"
        set +e
        acme.sh --issue --stateless -d "$ACME_DOMAIN" --server "$ACME_SERVER"
        ACME_EXIT_CODE="$?"
        set -e
        if [ "$ACME_EXIT_CODE" = 0 ]; then
            echo "ACME certificate generated successfully"
        elif [ "$ACME_EXIT_CODE" = 2 ]; then
            echo "Skipping certificate renewal, there's a valid one already"
        else
            echo "ACME certificate generation failed with exit code $ACME_EXIT_CODE"
            exit "$ACME_EXIT_CODE"
        fi

        while true; do
            # Deploy the certificate to HAProxy
            echo "Deploying certificate to HAProxy..."
            DEPLOY_HAPROXY_HOT_UPDATE=yes \
                DEPLOY_HAPROXY_STATS_SOCKET=/var/run/haproxy.sock \
                DEPLOY_HAPROXY_PEM_NAME="chain.pem" \
                DEPLOY_HAPROXY_PEM_PATH=/certs \
                acme.sh --deploy --deploy-hook haproxy -d "$ACME_DOMAIN"

            if curl "https://$ACME_DOMAIN" &> /dev/null; then
                break
            fi

            echo "Certificate deployment failed, retrying in 2 seconds..."
            sleep 2
        done

    else
        echo "Unknown ACME command '$1'"
        exit 1
    fi
fi
