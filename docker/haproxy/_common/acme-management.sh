#!/usr/bin/env sh

set -e

# Overridable for the test suite; the defaults are the container paths used in production.
ACME_HOME="${ACME_HOME:-/etc/acme}"
ACME_CRONTAB="${ACME_CRONTAB:-/etc/crontabs/root}"

export LE_WORKING_DIR="$ACME_HOME"

# The ACME home holds acme.sh's account private key, so keep it owner-only.
mkdir -p "$ACME_HOME"
chmod 700 "$ACME_HOME" 2>/dev/null || true

# This is done to prevent crashes
touch "$ACME_HOME/account-thumbprint"

# This is done to prevent acme.sh from throwing weird error messages
LOG_LEVEL=""

# `acme.sh --cron` renews every cert under the ACME home (branding domains too),
# so it must run on every boot regardless of whether the main domain uses ACME.
setup_cron() {
    echo "Configuring acme.sh renewal cron"
    mkdir -p "$(dirname "$ACME_CRONTAB")"
    echo "0 2 * * * /usr/local/bin/acme-cron.sh" > "$ACME_CRONTAB"
    if ! pgrep crond >/dev/null 2>&1; then
        crond
    fi
}

setup_cron

case "$1" in
    register)
        # HTTP-01 account registration; the thumbprint answers stateless challenges.
        if [ -n "$ACME_EMAIL" ]; then
            # Capture first: redirecting straight into the file would truncate it on failure.
            echo "Registering ACME account '$ACME_EMAIL' for $ACME_SERVER"
            thumbprint="$(acme.sh --register-account --email "$ACME_EMAIL" --server "$ACME_SERVER" \
                | grep ACCOUNT_THUMBPRINT \
                | awk -F'ACCOUNT_THUMBPRINT=' '{ print $2 }' | xargs)"

            if [ -n "$thumbprint" ]; then
                printf '%s\n' "$thumbprint" > "$ACME_HOME/account-thumbprint"
            elif [ -s "$ACME_HOME/account-thumbprint" ]; then
                echo "WARNING: ACME registration returned no thumbprint, keeping the stored one"
            else
                echo "ERROR: ACME registration returned no thumbprint and none is stored, http-01 validation will fail"
                exit 1
            fi
        fi
        ;;

    generate)
        # Cron is armed above; this branch covers only the MAIN domain.
        if [ -n "$ACME_DOMAIN" ] && [ -n "$ACME_EMAIL" ]; then
            # Generate the main domain cert, retrying (bounded) until HAProxy serves it.
            # A persistent failure must fall back to self-signed and let the cron retry,
            # not block boot.
            attempts=0
            max_attempts=30
            served=false
            while [ "$attempts" -lt "$max_attempts" ]; do
                attempts=$((attempts + 1))

                # A failed attempt must not abort the loop (set -e would kill the script).
                if ! acme-generate-cert.sh "$ACME_DOMAIN"; then
                    echo "Main-domain certificate issuance attempt $attempts failed"
                fi

                # Check the served cert actually covers the domain: a self-signed
                # *.localdomain cert always answers TLS. -checkhost matches the name
                # without validating the chain, deliberately -- chain validation would
                # break installs issuing from a non-public CA (letsencrypt_test, internal CA).
                if echo | openssl s_client -connect "127.0.0.1:$HTTPS_PORT" -servername "$ACME_DOMAIN" 2>/dev/null \
                    | openssl x509 -noout -checkhost "$ACME_DOMAIN" > /dev/null 2>&1; then
                    echo "Main-domain certificate is being served"
                    served=true
                    break
                fi

                echo "Certificate not yet available, retrying in 2 seconds..."
                sleep 2
            done

            if [ "$served" != "true" ]; then
                echo "Giving up main-domain issuance after $attempts attempts; the renewal cron will retry"
            fi
        fi
        ;;

    ""|cron)
        # Cron-only: nothing to issue, but the renewal cron above is armed.
        ;;

    *)
        echo "Unknown ACME command '$1'"
        exit 1
        ;;
esac
