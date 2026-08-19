#!/bin/bash
#===============================================================================
# Suite: acme-generate-cert.sh
#===============================================================================
# Pins that concurrent issuance is serialized and that the acme.sh exit codes
# are classified correctly.
#
# Why serialization matters: two independent callers drive this same script
# against the same acme.sh account and the same ACME home. The portal boot path
# (acme-management.sh) issues the main domain, and haproxy-sync calls it once
# per per-category branding domain whenever apiv4 pushes a DomainSync. acme.sh
# keeps its account state and per-domain state as files under the ACME home and
# is not concurrency-safe, so overlapping runs can corrupt that state or burn
# CA rate limit on duplicate orders.
#
# Exit code 2 is acme.sh's "a valid certificate already exists" and is the
# no-op fast path the whole design leans on to make repeated startup and
# reconnect pushes harmless.
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
cleanup_suite() { [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"; }
trap cleanup_suite EXIT

# new_fixture <issue_exit_code> [hold_seconds]
#
# The acme.sh stub records ENTER/EXIT around its body so an overlap between two
# concurrent runs is visible in the ordering of the trace, and optionally holds
# the lock for a while so the race has time to happen.
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
case " \$* " in
    *" --issue "*)
        echo "ENTER" >> "$WORK_DIR/log/trace.log"
        [ "$hold" -gt 0 ] && sleep $hold
        echo "EXIT" >> "$WORK_DIR/log/trace.log"
        echo "\$@" >> "$WORK_DIR/log/issue.log"
        exit $issue_rc
        ;;
    *" --deploy "*)
        echo "\$@" >> "$WORK_DIR/log/deploy.log"
        # The deploy hook is what puts the PEM where the crt-list expects it.
        echo "PEM" > "$CERTS_DIR/\$DEPLOY_HAPROXY_PEM_NAME"
        exit 0
        ;;
esac
exit 0
EOF
    chmod +x "$BIN_DIR"/*
}

# run_issue <domain> [pem_name]
run_issue() {
    RUN_OUT=$(
        env \
            PATH="$BIN_DIR:/usr/bin:/bin" \
            ACME_HOME="$ACME_HOME_DIR" \
            ACME_CERTS_DIR="$CERTS_DIR" \
            ACME_SERVER=letsencrypt \
            sh "$SCRIPT" "$@" 2>&1
    )
    RUN_RC=$?
}

lock_file() { echo "$ACME_HOME_DIR/.acme-issue.lock"; }

#-------------------------------------------------------------------------------
# Serialization: the reason this commit exists
#-------------------------------------------------------------------------------

new_fixture 0 0
run_issue vdi.example.com
check "a successful issuance exits 0" '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "issuance takes a lock under the ACME home" \
    '[ -e "$(lock_file)" ]' "out=$RUN_OUT"

# Two concurrent issuances must not interleave. Without the lock the trace is
# ENTER ENTER EXIT EXIT; with it, ENTER EXIT ENTER EXIT.
new_fixture 0 1
run_issue first.example.com pem-a.pem &
FIRST_PID=$!
# Give the first run time to enter the critical section before the second asks.
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

new_fixture 2 0
run_issue vdi.example.com
check "exit code 2 (valid cert already exists) is a success" \
    '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "exit code 2 says it is skipping the renewal" \
    'echo "$RUN_OUT" | grep -qi "valid one already"' "out=$RUN_OUT"
check "exit code 2 still deploys the existing certificate" \
    '[ -f "$WORK_DIR/log/deploy.log" ]' "out=$RUN_OUT"

new_fixture 1 0
run_issue vdi.example.com
check "a real issuance failure propagates its exit code" \
    '[ "$RUN_RC" -eq 1 ]' "rc=$RUN_RC out=$RUN_OUT"
check "a real issuance failure does not deploy" \
    '[ ! -f "$WORK_DIR/log/deploy.log" ]' "out=$RUN_OUT"

#-------------------------------------------------------------------------------
# The lock must not leak the critical section past a failure
#-------------------------------------------------------------------------------

new_fixture 1 0
run_issue first.example.com
# A second run after a failed one must still be able to take the lock. `timeout`
# reports 124 when it has to kill the child, which is what a leaked lock looks
# like. Capture that status explicitly: reading $? from inside check() would
# observe check's own call, not this run, and the assertion would never fail.
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

new_fixture 0 0
run_issue vdi.example.com custom-name.pem
check "the requested PEM name is what gets deployed" \
    'grep -q "custom-name.pem" "$WORK_DIR/log/deploy.log" 2>/dev/null || [ -f "$CERTS_DIR/custom-name.pem" ]' \
    "deploy=$(cat "$WORK_DIR/log/deploy.log" 2>/dev/null)"

#-------------------------------------------------------------------------------

echo "1..$TESTS"
if [ "$FAILURES" -gt 0 ]; then
    echo "FAILED: $FAILURES of $TESTS checks" >&2
    exit 1
fi
echo "PASSED: all $TESTS checks"
