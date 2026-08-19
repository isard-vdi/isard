#!/bin/bash
#===============================================================================
# Suite: acme-management.sh
#===============================================================================
# Pins that the renewal cron is configured on EVERY boot, before and regardless
# of any main-domain issuance branch.
#
# Why this matters: per-category branding domains are issued by haproxy-sync
# over HTTP-01 and land under /etc/acme just like the main domain, but until
# now the whole script sat inside `if [ -n "$ACME_DOMAIN" ] && [ -n
# "$ACME_EMAIL" ]`. An install whose main domain does not use ACME therefore
# configured no crond and no `acme.sh --cron` at all, and every branding
# certificate silently expired after 90 days.
#
# The script is driven as a real subprocess with stubbed acme.sh / crond /
# curl / acme-generate-cert.sh on PATH, and with its two filesystem locations
# redirected through ACME_HOME / ACME_CRONTAB so the suite never touches the
# host's /etc.
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
# Fixture: a throwaway root with stubbed binaries that record their invocations
#-------------------------------------------------------------------------------

WORK_DIR=""

cleanup_suite() { [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"; }
trap cleanup_suite EXIT

# new_fixture [curl_exit_code]
#
# Sets WORK_DIR, ACME_HOME_DIR, CRONTAB_FILE and BIN_DIR. Stubs write one line
# per invocation into $WORK_DIR/log/<name>.log so assertions can look at both
# "was it called" and "with what".
new_fixture() {
    local curl_rc="${1:-0}"

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

    cat >"$BIN_DIR/curl" <<EOF
#!/bin/sh
echo "\$@" >> "$WORK_DIR/log/curl.log"
exit $curl_rc
EOF

    # The boot retry sleeps between attempts; make that instant so a suite that
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
# Executes the script under test with a clean, explicit environment. Captures
# stdout+stderr into RUN_OUT and the exit status into RUN_RC.
run_acme() {
    local command="$1"
    shift

    RUN_OUT=$(
        env \
            PATH="$BIN_DIR:/usr/bin:/bin" \
            ACME_HOME="$ACME_HOME_DIR" \
            ACME_CRONTAB="$CRONTAB_FILE" \
            HTTPS_PORT=443 \
            ACME_SERVER=letsencrypt \
            "$@" \
            timeout 30 sh "$SCRIPT" "$command" 2>&1
    )
    RUN_RC=$?
}

# The bound the boot retry must respect. Kept in step with acme-management.sh.
# shellcheck disable=SC2034  # used inside the single-quoted conditions check() evals later
MAX_BOOT_ATTEMPTS=30

log_has() { [ -f "$WORK_DIR/log/$1" ]; }

#-------------------------------------------------------------------------------
# The regression this commit fixes: cron with no main-domain ACME config at all
#-------------------------------------------------------------------------------

new_fixture
run_acme generate
check "generate without ACME_EMAIL/ACME_DOMAIN succeeds" \
    '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "generate without ACME config still writes the renewal crontab" \
    '[ -f "$CRONTAB_FILE" ]' "out=$RUN_OUT"
check "the crontab entry runs acme.sh --cron over the whole ACME home" \
    'grep -q -- "--cron" "$CRONTAB_FILE" && grep -q -- "--home" "$CRONTAB_FILE"' \
    "crontab=$( [ -f "$CRONTAB_FILE" ] && cat "$CRONTAB_FILE")"
check "generate without ACME config starts crond" \
    'log_has crond.log'
check "generate without ACME config issues no main-domain certificate" \
    '! log_has acme-generate-cert.sh.log'

#-------------------------------------------------------------------------------
# The cron must not depend on the *register* branch either
#-------------------------------------------------------------------------------

new_fixture
run_acme register
check "register without ACME_EMAIL succeeds" \
    '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "register without ACME_EMAIL still writes the renewal crontab" \
    '[ -f "$CRONTAB_FILE" ]' "out=$RUN_OUT"
check "register without ACME_EMAIL registers no account" \
    '! log_has acme.sh.log'

#-------------------------------------------------------------------------------
# A bare / cron-only invocation is a supported no-op that still arms the cron
#-------------------------------------------------------------------------------

new_fixture
run_acme cron
check "cron subcommand succeeds" '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "cron subcommand writes the renewal crontab" '[ -f "$CRONTAB_FILE" ]'
check "cron subcommand issues nothing" '! log_has acme-generate-cert.sh.log'

#-------------------------------------------------------------------------------
# Existing behaviour that must not regress
#-------------------------------------------------------------------------------

new_fixture
run_acme register ACME_EMAIL=ops@example.com ACME_DOMAIN=vdi.example.com
check "register with ACME_EMAIL calls acme.sh --register-account" \
    'log_has acme.sh.log && grep -q -- "--register-account" "$WORK_DIR/log/acme.sh.log"' \
    "out=$RUN_OUT"
check "register with ACME_EMAIL stores the account thumbprint" \
    'grep -q "stub-thumbprint-value" "$ACME_HOME_DIR/account-thumbprint"' \
    "thumbprint=$(cat "$ACME_HOME_DIR/account-thumbprint" 2>/dev/null)"

new_fixture
run_acme generate ACME_EMAIL=ops@example.com ACME_DOMAIN=vdi.example.com
check "generate with full ACME config succeeds" \
    '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "generate with full ACME config writes the renewal crontab" \
    '[ -f "$CRONTAB_FILE" ]'
check "generate with full ACME config issues the main-domain certificate" \
    'log_has acme-generate-cert.sh.log && grep -q "vdi.example.com" "$WORK_DIR/log/acme-generate-cert.sh.log"' \
    "out=$RUN_OUT"

new_fixture
run_acme bogus-subcommand
check "an unknown subcommand is rejected" '[ "$RUN_RC" -ne 0 ]' "rc=$RUN_RC out=$RUN_OUT"

#-------------------------------------------------------------------------------
# The boot retry must be bounded, and must actually consult the probe
#-------------------------------------------------------------------------------
#
# The loop used to be `while true`. Nobody noticed because its exit probe is
# `curl -k`, which skips chain and hostname verification and so succeeds as
# soon as HAProxy answers TLS with anything at all: the loop left on the first
# pass whether or not ACME had issued a thing. These checks drive the probe
# from the stub instead, so the retry budget is exercised for real.

new_fixture 1   # probe always fails
run_acme generate ACME_EMAIL=ops@example.com ACME_DOMAIN=vdi.example.com
check "a failing probe does not end the retry loop after one attempt" \
    '[ "$(attempts_made)" -gt 1 ]' "attempts=$(attempts_made) out=$RUN_OUT"
check "a failing probe exhausts exactly the documented retry budget" \
    '[ "$(attempts_made)" -eq "$MAX_BOOT_ATTEMPTS" ]' "attempts=$(attempts_made)"
check "exhausting the retry budget terminates instead of looping forever" \
    '[ "$RUN_RC" -ne 124 ]' "rc=$RUN_RC (124 means the timeout killed it)"
check "exhausting the retry budget is not a fatal error" \
    '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "giving up is announced so the log explains the fallback" \
    'echo "$RUN_OUT" | grep -qi "giving up"' "out=$RUN_OUT"

new_fixture 0   # probe succeeds immediately
run_acme generate ACME_EMAIL=ops@example.com ACME_DOMAIN=vdi.example.com
check "a succeeding probe stops after a single attempt" \
    '[ "$(attempts_made)" -eq 1 ]' "attempts=$(attempts_made) out=$RUN_OUT"
check "a succeeding probe does not claim it gave up" \
    '! echo "$RUN_OUT" | grep -qi "giving up"' "out=$RUN_OUT"

# A transient issuance failure must not abort the loop: `set -e` used to kill
# the whole script on the first non-zero exit from acme-generate-cert.sh, so a
# CA hiccup during boot meant no further attempts at all.
new_fixture 1
cat >"$BIN_DIR/acme-generate-cert.sh" <<EOF
#!/bin/sh
echo "\$@" >> "$WORK_DIR/log/acme-generate-cert.sh.log"
exit 1
EOF
chmod +x "$BIN_DIR/acme-generate-cert.sh"
run_acme generate ACME_EMAIL=ops@example.com ACME_DOMAIN=vdi.example.com
check "a failing issuance attempt does not abort the retry loop" \
    '[ "$(attempts_made)" -eq "$MAX_BOOT_ATTEMPTS" ]' "attempts=$(attempts_made) out=$RUN_OUT"
check "a failing issuance attempt leaves the script exiting cleanly" \
    '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"

#-------------------------------------------------------------------------------
# The ACME home holds account keys: it must not be world-readable
#-------------------------------------------------------------------------------

new_fixture
run_acme generate
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
