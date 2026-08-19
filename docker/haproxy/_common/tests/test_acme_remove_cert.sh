#!/bin/bash
#===============================================================================
# Suite: acme-remove-cert.sh
#===============================================================================
# acme.sh indexes a certificate by its FIRST -d, so the on-disk state lives in
# <primary>_ecc and removal has to name the same primary the certificate was
# issued with. When the primary changes, the old directory is orphaned: nothing
# serves the certificate any more, but `acme.sh --cron` keeps renewing it
# forever, quietly spending CA rate limit on a certificate nobody uses.
#
# These checks pin that removal cleans the current primary and, when told about
# a previous one, that stale directory too.
#
# Run it with: make test-haproxy-acme
#===============================================================================

set -u -o pipefail

TESTS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT="$TESTS_DIR/../acme-remove-cert.sh"

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

WORK_DIR=""
cleanup_suite() { [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"; return 0; }
trap cleanup_suite EXIT

new_fixture() {
    [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"
    WORK_DIR=$(mktemp -d)
    ACME_HOME_DIR="$WORK_DIR/etc/acme"
    CERTS_DIR="$WORK_DIR/certs"
    BIN_DIR="$WORK_DIR/bin"

    mkdir -p "$BIN_DIR" "$WORK_DIR/log" "$ACME_HOME_DIR" "$CERTS_DIR"

    cat >"$BIN_DIR/acme.sh" <<EOF
#!/bin/sh
for a in "\$@"; do echo "\$a" >> "$WORK_DIR/log/remove.argv"; done
exit 0
EOF
    chmod +x "$BIN_DIR"/*
}

# seed_cert <name> <pem> — the on-disk state acme.sh leaves for a certificate
seed_cert() {
    mkdir -p "$ACME_HOME_DIR/$1_ecc"
    echo "state" > "$ACME_HOME_DIR/$1_ecc/$1.conf"
    echo "PEM" > "$CERTS_DIR/$2"
}

run_remove() {
    RUN_OUT=$(
        env \
            PATH="$BIN_DIR:/usr/bin:/bin" \
            ACME_HOME="$ACME_HOME_DIR" \
            ACME_CERTS_DIR="$CERTS_DIR" \
            timeout 30 sh "$SCRIPT" "$@" 2>&1
    )
    RUN_RC=$?
}

removed_names() { awk '/^-d$/ { getline; print }' "$WORK_DIR/log/remove.argv" 2>/dev/null; }

#-------------------------------------------------------------------------------
# The behaviour that already existed
#-------------------------------------------------------------------------------

new_fixture
seed_cert "gone.example.com" "gone.example.com.pem"
run_remove gone.example.com gone.example.com.pem
check "removing a certificate succeeds" '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "acme.sh is told to stop renewing it" \
    '[ "$(removed_names)" = "gone.example.com" ]' "removed=[$(removed_names)]"
check "the acme.sh state directory is cleaned" \
    '[ ! -d "$ACME_HOME_DIR/gone.example.com_ecc" ]' \
    "left=$(ls "$ACME_HOME_DIR" 2>/dev/null)"
check "the deployed PEM is deleted" \
    '[ ! -f "$CERTS_DIR/gone.example.com.pem" ]' "certs=$(ls "$CERTS_DIR")"

#-------------------------------------------------------------------------------
# The orphan this commit fixes: the previous primary
#-------------------------------------------------------------------------------

new_fixture
seed_cert "old-primary.example.com" "old.pem"
seed_cert "new-primary.example.com" "new-primary.example.com.pem"
run_remove new-primary.example.com new-primary.example.com.pem old-primary.example.com
check "a renamed primary is removed as well" \
    '[ "$(removed_names | tr "\n" " ")" = "new-primary.example.com old-primary.example.com " ]' \
    "removed=[$(removed_names | tr '\n' ' ')]"
check "the stale acme.sh state directory is cleaned too" \
    '[ ! -d "$ACME_HOME_DIR/old-primary.example.com_ecc" ]' \
    "left=$(ls "$ACME_HOME_DIR" 2>/dev/null)"
check "the current primary state directory is cleaned" \
    '[ ! -d "$ACME_HOME_DIR/new-primary.example.com_ecc" ]' \
    "left=$(ls "$ACME_HOME_DIR" 2>/dev/null)"

# Passing the same value twice must not turn into a second removal.
new_fixture
seed_cert "same.example.com" "same.pem"
run_remove same.example.com same.pem same.example.com
check "a previous primary equal to the current one is not removed twice" \
    '[ "$(removed_names | wc -l)" -eq 1 ]' "removed=[$(removed_names | tr '\n' ' ')]"

new_fixture
seed_cert "solo.example.com" "solo.pem"
run_remove solo.example.com solo.pem
check "omitting the previous primary removes only the current one" \
    '[ "$(removed_names | wc -l)" -eq 1 ]' "removed=[$(removed_names | tr '\n' ' ')]"

#-------------------------------------------------------------------------------
# A name is one argv element, never a fragment of a joined string
#-------------------------------------------------------------------------------

new_fixture
seed_cert "odd name.example.com" "odd.pem"
run_remove "odd name.example.com" odd.pem
check "a name containing spaces stays a single argument" \
    '[ "$(removed_names)" = "odd name.example.com" ]' "removed=[$(removed_names)]"

#-------------------------------------------------------------------------------

echo "1..$TESTS"
if [ "$FAILURES" -gt 0 ]; then
    echo "FAILED: $FAILURES of $TESTS checks" >&2
    exit 1
fi
echo "PASSED: all $TESTS checks"
