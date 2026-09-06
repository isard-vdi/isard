#!/bin/bash
#===============================================================================
# Suite: acme-management.sh
#===============================================================================
# Two things are pinned here.
#
# 1. The renewal cron is configured on EVERY boot, before and regardless of any
#    main-domain issuance branch. Per-category branding domains are issued by
#    haproxy-sync over HTTP-01 and land under the ACME home just like the main
#    domain, but the whole script used to sit inside `if [ -n "$ACME_DOMAIN" ]
#    && [ -n "$ACME_EMAIL" ]`. An install whose main domain does not use ACME
#    configured no crond at all, and every branding certificate silently
#    expired after 90 days.
#
# 2. The boot retry is bounded AND its exit probe tests the right thing. HAProxy
#    serves a certificate from its first second (auto-generate-certs.sh mints a
#    local CA and signs a *.localdomain host certificate with it), so a probe
#    that merely establishes TLS succeeds immediately whether or not ACME issued
#    anything. The probe checks the served certificate's NAME instead, driven
#    here against a real TLS listener rather than a stub.
#
# acme.sh, crond and the issuance script are stubbed on PATH; the script's two
# filesystem locations are redirected through ACME_HOME / ACME_CRONTAB so the
# suite never touches the host's /etc.
#
# Run it with: make test-haproxy-acme
#===============================================================================

set -u -o pipefail

TESTS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT="$TESTS_DIR/../acme-management.sh"

if [ ! -f "$SCRIPT" ]; then
    echo "FATAL: $SCRIPT not found" >&2
    exit 2
fi

for cmd in openssl timeout; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "FATAL: $cmd is required by this suite" >&2
        exit 2
    fi
done

# Nothing may listen here: it is how the suite simulates "HAProxy is not
# serving a certificate for this name yet".
CLOSED_PORT=14499
if (echo >"/dev/tcp/127.0.0.1/$CLOSED_PORT") 2>/dev/null; then
    echo "FATAL: port $CLOSED_PORT is in use; the suite needs it closed" >&2
    exit 2
fi

PROBE_DOMAIN="vdi.example.com"

TESTS=0
FAILURES=0

pass() { TESTS=$((TESTS + 1)); echo "ok $TESTS - $1"; }
fail() {
    TESTS=$((TESTS + 1))
    FAILURES=$((FAILURES + 1))
    echo "not ok $TESTS - $1"
    [ $# -gt 1 ] && echo "  # $2"
    return 0
}

check() {
    local name="$1" condition="$2" detail="${3:-}"
    if eval "$condition"; then
        pass "$name"
    else
        fail "$name" "failed: $condition${detail:+ | $detail}"
    fi
}

#-------------------------------------------------------------------------------
# Fixtures
#-------------------------------------------------------------------------------

WORK_DIR=""
CERT_DIR=""
SERVER_PID=""
PROBE_PORT=""

cleanup_suite() {
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
    [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"
    [ -n "$CERT_DIR" ] && rm -rf "$CERT_DIR"
    return 0
}
trap cleanup_suite EXIT

# new_fixture — a throwaway root with stubs that record their invocations.
# Deliberately does NOT stub the probe: that is exercised for real.
new_fixture() {
    [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"
    WORK_DIR=$(mktemp -d)
    ACME_HOME_DIR="$WORK_DIR/etc/acme"
    CRONTAB_FILE="$WORK_DIR/etc/crontabs/root"
    BIN_DIR="$WORK_DIR/bin"

    mkdir -p "$BIN_DIR" "$WORK_DIR/log" "$(dirname "$CRONTAB_FILE")"

    cat >"$BIN_DIR/acme.sh" <<EOF
#!/bin/sh
echo "\$@" >> "$WORK_DIR/log/acme.sh.log"
# The register path pipes stdout through grep/awk to extract the thumbprint.
echo "ACCOUNT_THUMBPRINT=stub-thumbprint-value"
exit 0
EOF

    cat >"$BIN_DIR/acme-generate-cert.sh" <<EOF
#!/bin/sh
echo "\$@" >> "$WORK_DIR/log/acme-generate-cert.sh.log"
exit 0
EOF

    cat >"$BIN_DIR/crond" <<EOF
#!/bin/sh
echo "started" >> "$WORK_DIR/log/crond.log"
exit 0
EOF

    # No crond running yet, so the script must start one.
    cat >"$BIN_DIR/pgrep" <<EOF
#!/bin/sh
exit 1
EOF

    # The boot retry sleeps between attempts; make that instant so a case that
    # deliberately exhausts the retry budget stays fast.
    cat >"$BIN_DIR/sleep" <<EOF
#!/bin/sh
exit 0
EOF

    chmod +x "$BIN_DIR"/*
}

# attempts_made — how many times the issuance script was invoked
attempts_made() { wc -l <"$WORK_DIR/log/acme-generate-cert.sh.log" 2>/dev/null | tr -d ' '; }

# run_acme <command> [VAR=VAL ...]
#
# HTTPS_PORT defaults to the closed port, so the probe fails unless a caller
# points it at a listener. Later assignments win, so callers can override it.
run_acme() {
    local command="$1"
    shift

    RUN_OUT=$(
        env \
            PATH="$BIN_DIR:/usr/bin:/bin" \
            ACME_HOME="$ACME_HOME_DIR" \
            ACME_CRONTAB="$CRONTAB_FILE" \
            HTTPS_PORT="$CLOSED_PORT" \
            ACME_SERVER=letsencrypt \
            "$@" \
            timeout 60 sh "$SCRIPT" "$command" 2>&1
    )
    RUN_RC=$?
}

# The bound the boot retry must respect. Kept in step with acme-management.sh.
# shellcheck disable=SC2034  # used inside the single-quoted conditions check() evals later
MAX_BOOT_ATTEMPTS=30

log_has() { [ -f "$WORK_DIR/log/$1" ]; }

# mint_certs — the boot certificate exactly as auto-generate-certs.sh makes it
# (a local CA, then a *.localdomain host certificate signed by it), plus the
# certificate ACME would have issued, which carries the requested name.
#
# The boot certificate is CA-signed, not self-signed, so "does the issuer equal
# the subject" would not separate the two cases either.
mint_certs() {
    CERT_DIR=$(mktemp -d)
    openssl genrsa -out "$CERT_DIR/ca-key.pem" 2048 >/dev/null 2>&1
    openssl req -new -x509 -days 9999 -key "$CERT_DIR/ca-key.pem" \
        -out "$CERT_DIR/ca-cert.pem" -sha256 \
        -subj "/C=CA/L=Barcelona/O=localdomain/CN=localdomain" >/dev/null 2>&1
    openssl genrsa -out "$CERT_DIR/boot-key.pem" 2048 >/dev/null 2>&1
    openssl req -new -key "$CERT_DIR/boot-key.pem" -sha256 \
        -out "$CERT_DIR/boot.csr" -subj "/CN=*.localdomain" >/dev/null 2>&1
    openssl x509 -req -days 9999 -in "$CERT_DIR/boot.csr" \
        -CA "$CERT_DIR/ca-cert.pem" -CAkey "$CERT_DIR/ca-key.pem" \
        -set_serial 1 -sha256 -out "$CERT_DIR/boot-cert.pem" >/dev/null 2>&1

    openssl req -new -x509 -days 9999 -newkey rsa:2048 -nodes \
        -keyout "$CERT_DIR/acme-key.pem" -out "$CERT_DIR/acme-cert.pem" \
        -subj "/CN=$PROBE_DOMAIN" \
        -addext "subjectAltName=DNS:$PROBE_DOMAIN" >/dev/null 2>&1

    [ -s "$CERT_DIR/boot-cert.pem" ] && [ -s "$CERT_DIR/acme-cert.pem" ]
}

# serve_cert <cert> <key> — sets PROBE_PORT and SERVER_PID, or returns 1.
# Assigns rather than echoing: a command substitution would run this in a
# subshell and the parent would never learn the pid it has to kill.
serve_cert() {
    local cert="$1" key="$2" port
    PROBE_PORT=""
    for port in 14443 14444 14445 14446 14447; do
        openssl s_server -accept "$port" -cert "$cert" -key "$key" -www \
            -naccept 200 >/dev/null 2>&1 &
        SERVER_PID=$!
        sleep 1
        if kill -0 "$SERVER_PID" 2>/dev/null; then
            PROBE_PORT="$port"
            return 0
        fi
    done
    SERVER_PID=""
    return 1
}

stop_server() {
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null
        wait "$SERVER_PID" 2>/dev/null
    fi
    SERVER_PID=""
}

#-------------------------------------------------------------------------------
# The cron must not depend on any main-domain ACME config
#-------------------------------------------------------------------------------

new_fixture
run_acme generate
check "generate without ACME_EMAIL/ACME_DOMAIN succeeds" \
    '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "generate without ACME config still writes the renewal crontab" \
    '[ -f "$CRONTAB_FILE" ]' "out=$RUN_OUT"
check "the crontab entry runs the acme renewal wrapper" \
    'grep -q -- "acme-cron.sh" "$CRONTAB_FILE"' \
    "crontab=$( [ -f "$CRONTAB_FILE" ] && cat "$CRONTAB_FILE")"
check "the renewal wrapper runs acme.sh --cron over the whole ACME home" \
    'grep -q -- "--cron" "$TESTS_DIR/../acme-cron.sh" && grep -q -- "--home" "$TESTS_DIR/../acme-cron.sh"' \
    "wrapper=$( [ -f "$TESTS_DIR/../acme-cron.sh" ] && cat "$TESTS_DIR/../acme-cron.sh")"
check "generate without ACME config starts crond" 'log_has crond.log'
check "generate without ACME config issues no main-domain certificate" \
    '! log_has acme-generate-cert.sh.log'

new_fixture
run_acme register
check "register without ACME_EMAIL succeeds" \
    '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "register without ACME_EMAIL still writes the renewal crontab" \
    '[ -f "$CRONTAB_FILE" ]' "out=$RUN_OUT"
check "register without ACME_EMAIL registers no account" '! log_has acme.sh.log'

new_fixture
run_acme cron
check "cron subcommand succeeds" '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "cron subcommand writes the renewal crontab" '[ -f "$CRONTAB_FILE" ]'
check "cron subcommand issues nothing" '! log_has acme-generate-cert.sh.log'

new_fixture
run_acme bogus-subcommand
check "an unknown subcommand is rejected" '[ "$RUN_RC" -ne 0 ]' "rc=$RUN_RC out=$RUN_OUT"

#-------------------------------------------------------------------------------
# Account registration
#-------------------------------------------------------------------------------

new_fixture
run_acme register ACME_EMAIL=ops@example.com ACME_DOMAIN="$PROBE_DOMAIN"
check "register with ACME_EMAIL calls acme.sh --register-account" \
    'log_has acme.sh.log && grep -q -- "--register-account" "$WORK_DIR/log/acme.sh.log"' \
    "out=$RUN_OUT"
check "register with ACME_EMAIL stores the account thumbprint" \
    'grep -q "stub-thumbprint-value" "$ACME_HOME_DIR/account-thumbprint"' \
    "thumbprint=$(cat "$ACME_HOME_DIR/account-thumbprint" 2>/dev/null)"

#-------------------------------------------------------------------------------
# The boot retry: bounded, resilient, and driven by a probe that means something
#-------------------------------------------------------------------------------

new_fixture
run_acme generate ACME_EMAIL=ops@example.com ACME_DOMAIN="$PROBE_DOMAIN"
check "generate with full ACME config issues the main-domain certificate" \
    'log_has acme-generate-cert.sh.log && grep -q "$PROBE_DOMAIN" "$WORK_DIR/log/acme-generate-cert.sh.log"' \
    "out=$RUN_OUT"
check "an unsatisfied probe does not end the retry loop after one attempt" \
    '[ "$(attempts_made)" -gt 1 ]' "attempts=$(attempts_made) out=$RUN_OUT"
check "an unsatisfied probe exhausts exactly the documented retry budget" \
    '[ "$(attempts_made)" -eq "$MAX_BOOT_ATTEMPTS" ]' "attempts=$(attempts_made)"
check "exhausting the retry budget terminates instead of looping forever" \
    '[ "$RUN_RC" -ne 124 ]' "rc=$RUN_RC (124 means the timeout killed it)"
check "exhausting the retry budget is not a fatal error" \
    '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "giving up is announced so the log explains the fallback" \
    'echo "$RUN_OUT" | grep -qi "giving up"' "out=$RUN_OUT"

# A transient issuance failure must not abort the loop: `set -e` used to kill
# the whole script on the first non-zero exit from acme-generate-cert.sh, so a
# CA hiccup during boot meant no further attempts at all.
new_fixture
cat >"$BIN_DIR/acme-generate-cert.sh" <<EOF
#!/bin/sh
echo "\$@" >> "$WORK_DIR/log/acme-generate-cert.sh.log"
exit 1
EOF
chmod +x "$BIN_DIR/acme-generate-cert.sh"
run_acme generate ACME_EMAIL=ops@example.com ACME_DOMAIN="$PROBE_DOMAIN"
check "a failing issuance attempt does not abort the retry loop" \
    '[ "$(attempts_made)" -eq "$MAX_BOOT_ATTEMPTS" ]' "attempts=$(attempts_made) out=$RUN_OUT"
check "a failing issuance attempt leaves the script exiting cleanly" \
    '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"

#-------------------------------------------------------------------------------
# The probe must test the SERVED CERTIFICATE'S NAME, not just that TLS answers
#-------------------------------------------------------------------------------

if ! mint_certs; then
    fail "could not mint the test certificates with openssl"
else
    new_fixture
    if ! serve_cert "$CERT_DIR/boot-cert.pem" "$CERT_DIR/boot-key.pem"; then
        fail "could not start a local TLS listener for the boot certificate"
    else
        run_acme generate ACME_EMAIL=ops@example.com ACME_DOMAIN="$PROBE_DOMAIN" \
            HTTPS_PORT="$PROBE_PORT"
        stop_server
        check "TLS answering with the boot certificate does not satisfy the probe" \
            '[ "$(attempts_made)" -eq "$MAX_BOOT_ATTEMPTS" ]' \
            "attempts=$(attempts_made) out=$RUN_OUT"
        check "the boot certificate case is reported as giving up" \
            'echo "$RUN_OUT" | grep -qi "giving up"' "out=$RUN_OUT"
    fi

    new_fixture
    if ! serve_cert "$CERT_DIR/acme-cert.pem" "$CERT_DIR/acme-key.pem"; then
        fail "could not start a local TLS listener for the issued certificate"
    else
        run_acme generate ACME_EMAIL=ops@example.com ACME_DOMAIN="$PROBE_DOMAIN" \
            HTTPS_PORT="$PROBE_PORT"
        stop_server
        check "a certificate carrying the requested name satisfies the probe" \
            '[ "$(attempts_made)" -eq 1 ]' "attempts=$(attempts_made) out=$RUN_OUT"
        check "satisfying the probe is reported as being served" \
            'echo "$RUN_OUT" | grep -qi "being served"' "out=$RUN_OUT"
        check "satisfying the probe does not claim it gave up" \
            '! echo "$RUN_OUT" | grep -qi "giving up"' "out=$RUN_OUT"
    fi
fi

#-------------------------------------------------------------------------------
# The ACME home holds account keys: it must not be world-readable
#-------------------------------------------------------------------------------

new_fixture
run_acme cron
check "the ACME home is created" '[ -d "$ACME_HOME_DIR" ]' "out=$RUN_OUT"
check "the ACME home is not group/world accessible" \
    '[ "$(stat -c %a "$ACME_HOME_DIR" 2>/dev/null)" = "700" ]' \
    "mode=$(stat -c %a "$ACME_HOME_DIR" 2>/dev/null)"

#-------------------------------------------------------------------------------

echo "1..$TESTS"
if [ "$FAILURES" -gt 0 ]; then
    echo "FAILED: $FAILURES of $TESTS checks" >&2
    exit 1
fi
echo "PASSED: all $TESTS checks"
