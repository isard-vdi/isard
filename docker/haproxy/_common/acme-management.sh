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
            # Generate the main domain certificate, retrying until HAProxy
            # serves it. Bounded: the exit-code-2 fast path already makes an
            # already-valid certificate a no-op, so the retry only exists to
            # ride out a slow start, and a persistent failure must fall back to
            # the self-signed certificate and let the renewal cron try later
            # rather than spin here forever holding the boot sequence.
            attempts=0
            max_attempts=30
            served=false
            while [ "$attempts" -lt "$max_attempts" ]; do
                attempts=$((attempts + 1))

                # A failed attempt must not abort the loop: `set -e` would
                # otherwise kill the whole script on the first CA hiccup.
                if ! acme-generate-cert.sh "$ACME_DOMAIN"; then
                    echo "Main-domain certificate issuance attempt $attempts failed"
                fi

                # Ask whether the certificate HAProxy is serving actually
                # covers the domain we just asked for. Checking only that TLS
                # answers is useless here: auto-generate-certs.sh has already
                # put a locally-signed *.localdomain certificate in place, so
                # something always answers.
                #
                # -checkhost does the full name match, SANs included, and reads
                # the certificate the server presents without validating its
                # chain. That last part is deliberate: chain validation would
                # break every install issuing from a non-public CA -- a
                # letsencrypt_test deployment, or a client's internal CA --
                # which would then burn the whole retry budget on every boot.
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
        # Cron-only invocation: nothing to issue, but the renewal cron above is
        # armed. Used by flavours and configs that serve no main-domain ACME
        # certificate yet still need branding certificates to renew.
        ;;

    *)
        echo "Unknown ACME command '$1'"
        exit 1
        ;;
esac
