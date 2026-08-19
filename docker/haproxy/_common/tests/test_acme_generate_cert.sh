#!/bin/bash
#===============================================================================
# Suite: acme-generate-cert.sh
#===============================================================================
# Pins three things.
#
# 1. Concurrent issuance is serialized. Two independent callers drive this
#    script against the same acme.sh account and ACME home: the portal boot
#    path issues the main domain, and haproxy-sync calls it once per
#    per-category branding domain on every DomainSync push. acme.sh keeps its
#    account and per-domain state as plain files there and is not
#    concurrency-safe.
#
# 2. acme.sh's exit codes are classified correctly. Exit 2 is "a valid
#    certificate already exists" and is the no-op fast path the whole design
#    leans on to make repeated startup and reconnect pushes harmless.
#
# 3. The certificate can carry several names, and every name reaches acme.sh as
#    its OWN argv element. A joined string would make a name containing a space
#    or a dash an argument-injection vector into acme.sh, so the suite asserts
#    argv boundaries rather than a flattened command line.
#
# Run it with: make test-haproxy-acme
#===============================================================================

set -u -o pipefail

TESTS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT="$TESTS_DIR/../acme-generate-cert.sh"

if [ ! -f "$SCRIPT" ]; then
    echo "FATAL: $SCRIPT not found" >&2
    exit 2
fi

if ! command -v flock >/dev/null 2>&1; then
    echo "FATAL: flock is required by this suite" >&2
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

WORK_DIR=""
cleanup_suite() { [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"; return 0; }
trap cleanup_suite EXIT

# new_fixture <issue_exit_code> [hold_seconds]
#
# The acme.sh stub records each invocation's argv ONE ARGUMENT PER LINE, which
# is what lets the assertions below talk about argv boundaries instead of a
# flattened string. It also traces entry and exit of the issue call so an
# overlap between two concurrent runs is visible in the ordering.
new_fixture() {
    local issue_rc="${1:-0}" hold="${2:-0}"

    [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"
    WORK_DIR=$(mktemp -d)
    ACME_HOME_DIR="$WORK_DIR/etc/acme"
    CERTS_DIR="$WORK_DIR/certs"
    BIN_DIR="$WORK_DIR/bin"

    mkdir -p "$BIN_DIR" "$WORK_DIR/log" "$ACME_HOME_DIR" "$CERTS_DIR"

    cat >"$BIN_DIR/acme.sh" <<EOF
#!/bin/sh
log_argv() {
    target="\$1"; shift
    for a in "\$@"; do echo "\$a" >> "$WORK_DIR/log/\$target"; done
}
case " \$* " in
    *" --register-account "*)
        log_argv register.argv "\$@"
        echo "ACCOUNT_THUMBPRINT=stub-thumbprint-value"
        exit 0
        ;;
    *" --issue "*)
        echo "ENTER" >> "$WORK_DIR/log/trace.log"
        [ "$hold" -gt 0 ] && sleep $hold
        echo "EXIT" >> "$WORK_DIR/log/trace.log"
        log_argv issue.argv "\$@"
        exit $issue_rc
        ;;
    *" --deploy "*)
        log_argv deploy.argv "\$@"
        echo "PEM" > "$CERTS_DIR/\$DEPLOY_HAPROXY_PEM_NAME"
        exit 0
        ;;
esac
exit 0
EOF
    chmod +x "$BIN_DIR"/*
}

run_issue() {
    RUN_OUT=$(
        env \
            PATH="$BIN_DIR:/usr/bin:/bin" \
            ACME_HOME="$ACME_HOME_DIR" \
            ACME_CERTS_DIR="$CERTS_DIR" \
            ACME_SERVER=letsencrypt \
            timeout 30 sh "$SCRIPT" "$@" 2>&1
    )
    RUN_RC=$?
}

# issued_names / deployed_names — the values that followed a -d, in order.
# Reading them out of the one-arg-per-line log is what makes "each name is its
# own argv element" an assertable property.
issued_names() { awk '/^-d$/ { getline; print }' "$WORK_DIR/log/issue.argv" 2>/dev/null; }
deployed_names() { awk '/^-d$/ { getline; print }' "$WORK_DIR/log/deploy.argv" 2>/dev/null; }
issue_has_arg() { grep -qxF -- "$1" "$WORK_DIR/log/issue.argv" 2>/dev/null; }
lock_file() { echo "$ACME_HOME_DIR/.acme-issue.lock"; }

#-------------------------------------------------------------------------------
# Backwards compatibility: the two call sites that exist today
#-------------------------------------------------------------------------------

# acme-management.sh calls it with the domain alone.
new_fixture 0
run_issue vdi.example.com
check "a single-name call still succeeds" '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "a single-name call issues exactly that name" \
    '[ "$(issued_names)" = "vdi.example.com" ]' "names=[$(issued_names)]"
check "a single-name call defaults the PEM to chain.pem" \
    '[ -f "$CERTS_DIR/chain.pem" ]' "certs=$(ls "$CERTS_DIR")"

# haproxy-sync calls it with (domain, pemName).
new_fixture 0
run_issue branding.example.com branding.example.com.pem
check "the positional PEM name still works" \
    '[ -f "$CERTS_DIR/branding.example.com.pem" ]' "certs=$(ls "$CERTS_DIR")"
check "the positional PEM name does not leak into the issued names" \
    '[ "$(issued_names)" = "branding.example.com" ]' "names=[$(issued_names)]"

#-------------------------------------------------------------------------------
# The ACME account: server and email
#-------------------------------------------------------------------------------

new_fixture 0
run_issue vdi.example.com chain.pem letsencrypt_test ops@example.com
check "an explicit ACME server is passed to acme.sh" \
    'issue_has_arg letsencrypt_test' "argv=$(cat "$WORK_DIR/log/issue.argv" 2>/dev/null | tr '\n' ' ')"
check "an email registers the ACME account" \
    '[ -f "$WORK_DIR/log/register.argv" ]' "out=$RUN_OUT"
check "the account is registered with the given email" \
    'grep -qxF -- "ops@example.com" "$WORK_DIR/log/register.argv"' \
    "argv=$(cat "$WORK_DIR/log/register.argv" 2>/dev/null | tr '\n' ' ')"
check "the account thumbprint is stored for the challenge responder" \
    'grep -q "stub-thumbprint-value" "$ACME_HOME_DIR/account-thumbprint"' \
    "thumbprint=$(cat "$ACME_HOME_DIR/account-thumbprint" 2>/dev/null)"

# Re-registering on every issuance would spend an ACME round trip each time.
new_fixture 0
printf 'already-registered\n' > "$ACME_HOME_DIR/account-thumbprint"
run_issue vdi.example.com chain.pem letsencrypt ops@example.com
check "an existing account is not registered again" \
    '[ ! -f "$WORK_DIR/log/register.argv" ]' "out=$RUN_OUT"
check "an existing account thumbprint is left alone" \
    'grep -q "already-registered" "$ACME_HOME_DIR/account-thumbprint"' \
    "thumbprint=$(cat "$ACME_HOME_DIR/account-thumbprint" 2>/dev/null)"

new_fixture 0
run_issue vdi.example.com chain.pem letsencrypt
check "no email means no account registration" \
    '[ ! -f "$WORK_DIR/log/register.argv" ]' "out=$RUN_OUT"

#-------------------------------------------------------------------------------
# Several names on one certificate
#-------------------------------------------------------------------------------

new_fixture 0
run_issue primary.example.com chain.pem letsencrypt ops@example.com \
    alt-one.example.com alt-two.example.com
check "every name is issued, primary first, in order" \
    '[ "$(issued_names | tr "\n" " ")" = "primary.example.com alt-one.example.com alt-two.example.com " ]' \
    "names=[$(issued_names | tr '\n' ' ')]"
check "the deploy hook is keyed on the primary name alone" \
    '[ "$(deployed_names)" = "primary.example.com" ]' "deployed=[$(deployed_names)]"
check "a multi-name issuance succeeds" '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"

# A name is one argv element or it is an injection vector: a value containing a
# space must not become two arguments to acme.sh.
new_fixture 0
run_issue primary.example.com chain.pem letsencrypt ops@example.com "evil name --force"
check "a name containing spaces stays a single argument" \
    '[ "$(issued_names | tail -1)" = "evil name --force" ]' \
    "names=[$(issued_names | tr '\n' '|')]"
check "a name containing spaces does not add stray arguments" \
    '[ "$(issued_names | wc -l)" -eq 2 ]' "count=$(issued_names | wc -l)"

#-------------------------------------------------------------------------------
# Serialization
#-------------------------------------------------------------------------------

new_fixture 0
run_issue vdi.example.com
check "issuance takes a lock under the ACME home" '[ -e "$(lock_file)" ]' "out=$RUN_OUT"

# Without the lock the trace is ENTER ENTER EXIT EXIT; with it, ENTER EXIT twice.
new_fixture 0 1
run_issue first.example.com pem-a.pem &
FIRST_PID=$!
sleep 0.2 2>/dev/null || sleep 1
run_issue second.example.com pem-b.pem &
SECOND_PID=$!
wait "$FIRST_PID" "$SECOND_PID"
TRACE=$(tr '\n' ' ' <"$WORK_DIR/log/trace.log" 2>/dev/null | sed 's/ *$//')
check "two concurrent issuances are serialized by the lock" \
    '[ "$TRACE" = "ENTER EXIT ENTER EXIT" ]' "trace=[$TRACE]"

#-------------------------------------------------------------------------------
# acme.sh exit-code classification
#-------------------------------------------------------------------------------

new_fixture 2
run_issue vdi.example.com
check "exit code 2 (valid cert already exists) is a success" \
    '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "exit code 2 says it is skipping the renewal" \
    'echo "$RUN_OUT" | grep -qi "valid one already"' "out=$RUN_OUT"
check "exit code 2 still deploys the existing certificate" \
    '[ -f "$WORK_DIR/log/deploy.argv" ]' "out=$RUN_OUT"

new_fixture 1
run_issue vdi.example.com
check "a real issuance failure propagates its exit code" \
    '[ "$RUN_RC" -eq 1 ]' "rc=$RUN_RC out=$RUN_OUT"
check "a real issuance failure does not deploy" \
    '[ ! -f "$WORK_DIR/log/deploy.argv" ]' "out=$RUN_OUT"

# A follow-up run must still be able to take the lock. timeout reports 124 when
# it has to kill the child, which is what a leaked lock looks like. Capture that
# explicitly: reading $? from inside check() would observe check's own call.
new_fixture 1
run_issue first.example.com
env PATH="$BIN_DIR:/usr/bin:/bin" ACME_HOME="$ACME_HOME_DIR" \
    ACME_CERTS_DIR="$CERTS_DIR" ACME_SERVER=letsencrypt \
    timeout 10 sh "$SCRIPT" second.example.com >/dev/null 2>&1
SECOND_RC=$?
check "the lock is released when issuance fails" \
    '[ "$SECOND_RC" -ne 124 ]' "rc=$SECOND_RC (124 = timed out waiting for the lock)"
check "a second run after a failure still reaches acme.sh" \
    '[ "$(wc -l <"$WORK_DIR/log/trace.log")" -eq 4 ]' \
    "trace lines=$(wc -l <"$WORK_DIR/log/trace.log" 2>/dev/null)"

#-------------------------------------------------------------------------------
# Deploy verification
#-------------------------------------------------------------------------------

new_fixture 0
run_issue vdi.example.com custom-name.pem
check "the requested PEM name is what gets deployed" \
    '[ -f "$CERTS_DIR/custom-name.pem" ]' "certs=$(ls "$CERTS_DIR")"

#-------------------------------------------------------------------------------

echo "1..$TESTS"
if [ "$FAILURES" -gt 0 ]; then
    echo "FAILED: $FAILURES of $TESTS checks" >&2
    exit 1
fi
echo "PASSED: all $TESTS checks"
