#!/usr/bin/env sh

set -e

# Filesystem locations. Overridable so the test suite
# (docker/haproxy/_common/tests/test_acme_management.sh) can drive this script
# without touching the host's /etc; the defaults are the container paths and
# are what production always uses.
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

# Configure the renewal cron.
#
# `acme.sh --cron` renews EVERY certificate under the ACME home: the main
# domain and every per-category branding domain that haproxy-sync issued over
# HTTP-01. This must therefore run on every boot, before any branching and
# regardless of whether the main domain itself uses ACME. It used to sit inside
# the `generate` branch, which in turn sat inside a guard on ACME_DOMAIN and
# ACME_EMAIL: an install whose main domain did not use ACME configured no crond
# at all, and its branding certificates silently expired after 90 days.
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
        # HTTP-01 account registration. The resulting thumbprint is what
        # HAProxy serves to answer the stateless challenge, so it is only
        # meaningful when the deployment configured an ACME account.
        if [ -n "$ACME_EMAIL" ]; then
            # The thumbprint answers every stateless http-01 challenge and outlives
            # the container, so redirecting into it would truncate it on a failure.
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
        # The cron is already armed above, which is the whole point: the branch
        # below only covers the MAIN domain, and it is skipped entirely on the
        # installs that configure no ACME account.
        if [ -n "$ACME_DOMAIN" ] && [ -n "$ACME_EMAIL" ]; then
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

            echo "ERROR: HAProxy has not loaded the certificate deployed to /certs/chain.pem after 60 seconds, it is still answering with the previous one" >&2
            exit 1
        fi
        ;;

    ""|cron)
        # Cron-only invocation: nothing to issue, but the renewal cron above is
        # armed. Used by flavours and configs that serve no main-domain ACME
        # certificate yet still need branding certificates to renew.
        ;;

    *)
        echo "Unknown ACME command '$1'"
        exit 1
        ;;
esac
