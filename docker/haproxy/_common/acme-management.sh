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

        acme-generate-cert.sh "$ACME_DOMAIN"

        # chain.pem always holds a certificate (the self-signed one), so only the
        # fingerprint tells whether HAProxy answers with the one just deployed
        deployed="$(openssl x509 -in /certs/chain.pem -noout -fingerprint -sha1 | cut -d= -f2 | tr -d ':')"

        attempt=1
        while [ "$attempt" -le 30 ]; do
            loaded="$(echo "show ssl cert /certs/chain.pem" \
                | socat -T2 - UNIX-CONNECT:/var/run/haproxy.sock \
                | awk '/^SHA1 FingerPrint:/ { print $3 }')"

            if [ -n "$loaded" ] && [ "$loaded" = "$deployed" ]; then
                echo "HAProxy has loaded the certificate for $ACME_DOMAIN"
                exit 0
            fi

            attempt=$((attempt + 1))
            sleep 2
        done

        echo "ERROR: HAProxy has not loaded the certificate deployed to /certs/chain.pem after 60 seconds, it is still answering with the previous one"
        exit 1
    else
        echo "Unknown ACME command '$1'"
        exit 1
    fi
fi
