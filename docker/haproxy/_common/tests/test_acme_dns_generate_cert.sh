#!/bin/bash
#===============================================================================
# Suite: acme-dns-generate-cert.sh
#===============================================================================
# HTTP-01 needs the name being certified to already point here and to answer on
# port 80. DNS-01 does not, which is why it exists: it is the only way to
# certify a name that is not pointed at this deployment yet. The price is a
# credential, and this suite is mostly about where that credential is allowed
# to appear.
#
# 1. The password never reaches argv. The reference implementation passed it as
#    the fifth positional argument, which puts it in /proc/<pid>/cmdline for the
#    whole issuance -- readable by anything else in the container, and dumped by
#    any `ps` an operator runs while debugging exactly the failure that made
#    them look. It comes in on stdin here, and the only place it is allowed to
#    end up is acme.sh's environment, because that is the sole interface the
#    dns_acmedns plugin offers.
#
# 2. Incomplete credentials are refused before acme.sh is called. Handing the
#    plugin three of four values produces a failure deep inside acme.sh whose
#    message is about DNS, not about configuration, and the operator goes
#    looking at their zone instead of at the form they just filled in.
#
# 3. Issuance is serialized against the HTTP-01 script, not just against itself.
#    Both drive the same acme.sh account and the same state directory, and a
#    deployment can legitimately have one domain on each challenge -- so the two
#    scripts have to share one lock, and this asserts that they do.
#
# 4. Exit 2 stays the no-op fast path, as everywhere else in this family.
#
# Run it with: make test-haproxy-acme
#===============================================================================

set -u -o pipefail

TESTS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT="$TESTS_DIR/../acme-dns-generate-cert.sh"
HTTP01_SCRIPT="$TESTS_DIR/../acme-generate-cert.sh"

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

PASSWORD='htB9mR9DYgcu9bX_afHF62erXaH2TS7bg9KW3F7Z'

# new_fixture <issue_exit_code> [hold_seconds]
#
# The acme.sh stub records argv one argument per line, and separately dumps the
# ACMEDNS_* variables it was handed. Keeping those two records apart is the
# whole point: it lets a test assert that the password is in one and not in the
# other, which is the property this script exists to provide.
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
    *" --issue "*)
        echo "ENTER" >> "$WORK_DIR/log/trace.log"
        # What the real dns_acmedns plugin prints: it quotes the update
        # request it sends to acme-dns, and the password is a header on it.
        echo "POST \$ACMEDNS_BASE_URL/update"
        echo "headers: X-Api-User: \$ACMEDNS_USERNAME X-Api-Key: \$ACMEDNS_PASSWORD"
        [ "$hold" -gt 0 ] && sleep $hold
        echo "EXIT" >> "$WORK_DIR/log/trace.log"
        log_argv issue.argv "\$@"
        {
            echo "ACMEDNS_BASE_URL=\${ACMEDNS_BASE_URL-<unset>}"
            echo "ACMEDNS_USERNAME=\${ACMEDNS_USERNAME-<unset>}"
            echo "ACMEDNS_PASSWORD=\${ACMEDNS_PASSWORD-<unset>}"
            echo "ACMEDNS_SUBDOMAIN=\${ACMEDNS_SUBDOMAIN-<unset>}"
        } > "$WORK_DIR/log/issue.env"
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

# run_issue [--no-password] [--unset <VAR>] [--] <script args...>
#
# Credentials travel in the environment, except the password, which is piped in.
run_issue() {
    local send_password=1
    local -a unset_vars=()
    while [ $# -gt 0 ]; do
        case "$1" in
            --no-password) send_password=0; shift ;;
            --unset) unset_vars+=("$2"); shift 2 ;;
            --) shift; break ;;
            *) break ;;
        esac
    done

    local -a all_env=(
        PATH="$BIN_DIR:/usr/bin:/bin"
        ACME_HOME="$ACME_HOME_DIR"
        ACME_CERTS_DIR="$CERTS_DIR"
        ACME_SERVER=letsencrypt
        ACMEDNS_BASE_URL=https://auth.example.com
        ACMEDNS_USERNAME=eabcdb41-d89f-4580-826f-3e62e9755ef2
        ACMEDNS_SUBDOMAIN=d420c923-bbd7-4056-ab64-c3ca54c9b3cf
    )
    # Filtered out rather than passed to `env -u`: `env -u X X=value` sets X
    # again, so unsetting alongside an assignment is a no-op.
    local -a env_args=()
    local assignment var skip
    for assignment in "${all_env[@]}"; do
        skip=0
        for var in "${unset_vars[@]+"${unset_vars[@]}"}"; do
            [ "${assignment%%=*}" = "$var" ] && skip=1
        done
        [ "$skip" -eq 0 ] && env_args+=("$assignment")
    done

    if [ "$send_password" -eq 1 ]; then
        RUN_OUT=$(printf '%s\n' "$PASSWORD" | env "${env_args[@]}" timeout 30 sh "$SCRIPT" "$@" 2>&1)
    else
        RUN_OUT=$(env "${env_args[@]}" timeout 30 sh "$SCRIPT" "$@" </dev/null 2>&1)
    fi
    RUN_RC=$?
}

issued_names() { awk '/^-d$/ { getline; print }' "$WORK_DIR/log/issue.argv" 2>/dev/null; }
issue_has_arg() { grep -qxF -- "$1" "$WORK_DIR/log/issue.argv" 2>/dev/null; }
issue_env() { cat "$WORK_DIR/log/issue.env" 2>/dev/null; }
lock_file() { echo "$ACME_HOME_DIR/.acme-issue.lock"; }

#-------------------------------------------------------------------------------
# The happy path
#-------------------------------------------------------------------------------

new_fixture 0
run_issue vdi.example.com
check "a dns-01 issuance succeeds" '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "it issues exactly the name it was given" \
    '[ "$(issued_names)" = "vdi.example.com" ]' "names=[$(issued_names)]"
check "it uses the acme-dns plugin" 'issue_has_arg "dns_acmedns"'
check "it asks for a dns challenge" 'issue_has_arg "--dns"'
check "it does not ask for the http-01 stateless mode" \
    '! issue_has_arg "--stateless"' "dns-01 and http-01 are alternatives, not a pair"
check "it defaults the PEM to chain.pem" '[ -f "$CERTS_DIR/chain.pem" ]' "certs=$(ls "$CERTS_DIR")"

new_fixture 0
run_issue branding.example.com branding.example.com.pem
check "a positional PEM name is honoured" \
    '[ -f "$CERTS_DIR/branding.example.com.pem" ]' "certs=$(ls "$CERTS_DIR")"

new_fixture 0
run_issue vdi.example.com chain.pem letsencrypt_test
check "a positional acme server is passed through" 'issue_has_arg "letsencrypt_test"'

#-------------------------------------------------------------------------------
# Where the password is allowed to be
#-------------------------------------------------------------------------------

new_fixture 0
run_issue vdi.example.com
check "the password reaches acme.sh through the environment" \
    'issue_env | grep -qxF "ACMEDNS_PASSWORD=$PASSWORD"' "env=$(issue_env)"
check "the password is NOT among acme.sh's arguments" \
    '! grep -qF -- "$PASSWORD" "$WORK_DIR/log/issue.argv"' \
    "argv would put it in /proc/<pid>/cmdline for anything in the container to read"
check "the other three credentials also travel in the environment" \
    'issue_env | grep -qxF "ACMEDNS_USERNAME=eabcdb41-d89f-4580-826f-3e62e9755ef2" && issue_env | grep -qxF "ACMEDNS_SUBDOMAIN=d420c923-bbd7-4056-ab64-c3ca54c9b3cf"' \
    "env=$(issue_env)"
check "the password is not echoed by the script" \
    '! grep -qF -- "$PASSWORD" <<<"$RUN_OUT"' "out=$RUN_OUT"

new_fixture 1
run_issue vdi.example.com
check "a failure does not echo the password either" \
    '! grep -qF -- "$PASSWORD" <<<"$RUN_OUT"' "out=$RUN_OUT"
check "a failure says where acme.sh's own output was kept" \
    'grep -qF -- "$ACME_HOME_DIR/acme-dns-last-run.log" <<<"$RUN_OUT"' "out=$RUN_OUT"
check "acme.sh's output is kept on disk, not thrown away" \
    'grep -qF -- "$PASSWORD" "$ACME_HOME_DIR/acme-dns-last-run.log"' \
    "the operator still needs to be able to diagnose the failure"
check "the kept output is readable only by its owner" \
    '[ "$(stat -c %a "$ACME_HOME_DIR/acme-dns-last-run.log")" = "600" ]' \
    "perms=$(stat -c %a "$ACME_HOME_DIR/acme-dns-last-run.log" 2>/dev/null)"

#-------------------------------------------------------------------------------
# Incomplete credentials
#-------------------------------------------------------------------------------

new_fixture 0
run_issue --no-password -- vdi.example.com
check "no password on stdin is refused" '[ "$RUN_RC" -ne 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "no password on stdin never reaches acme.sh" \
    '[ ! -f "$WORK_DIR/log/issue.argv" ]' \
    "acme.sh would fail with a message about DNS, not about configuration"

for missing in ACMEDNS_BASE_URL ACMEDNS_USERNAME ACMEDNS_SUBDOMAIN; do
    new_fixture 0
    run_issue --unset "$missing" -- vdi.example.com
    check "a missing $missing is refused" '[ "$RUN_RC" -ne 0 ]' "rc=$RUN_RC out=$RUN_OUT"
    check "a missing $missing names itself in the message" \
        'grep -qF -- "$missing" <<<"$RUN_OUT"' "out=$RUN_OUT"
    check "a missing $missing never reaches acme.sh" '[ ! -f "$WORK_DIR/log/issue.argv" ]'
done

new_fixture 0
run_issue
check "no domain is refused" '[ "$RUN_RC" -ne 0 ]' "rc=$RUN_RC out=$RUN_OUT"

#-------------------------------------------------------------------------------
# More than one name
#-------------------------------------------------------------------------------
# A multi-name certificate over acme-dns is not the same problem as over
# HTTP-01: one acme.sh invocation uses ONE acme-dns account for every name on
# the certificate, and an account holds a bounded number of TXT records. That
# needs a design, and until it has one this refuses loudly. Issuing a
# certificate silently missing a name is the bad outcome -- the second name
# fails TLS in a browser, nowhere near anything that mentions certificates.

new_fixture 0
run_issue vdi.example.com chain.pem letsencrypt extra.example.com
check "a second name is refused rather than dropped" '[ "$RUN_RC" -ne 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "a second name never reaches acme.sh" '[ ! -f "$WORK_DIR/log/issue.argv" ]'
check "the refusal names the argument it did not expect" \
    'grep -qF -- "extra.example.com" <<<"$RUN_OUT"' "out=$RUN_OUT"

#-------------------------------------------------------------------------------
# acme.sh exit codes
#-------------------------------------------------------------------------------

new_fixture 2
run_issue vdi.example.com
check "exit 2 is the no-op fast path" '[ "$RUN_RC" -eq 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "exit 2 still deploys" '[ -f "$CERTS_DIR/chain.pem" ]' \
    "a valid certificate already exists, but this container may not have it yet"

new_fixture 1
run_issue vdi.example.com
check "a real failure propagates" '[ "$RUN_RC" -ne 0 ]' "rc=$RUN_RC out=$RUN_OUT"
check "a real failure does not deploy" '[ ! -f "$CERTS_DIR/chain.pem" ]' \
    "certs=$(ls "$CERTS_DIR")"

#-------------------------------------------------------------------------------
# Serialization, including against the HTTP-01 script
#-------------------------------------------------------------------------------

new_fixture 0 2
(run_issue vdi.example.com) &
FIRST=$!
sleep 0.4
(run_issue other.example.com) &
SECOND=$!
wait $FIRST $SECOND
check "two dns-01 issuances do not interleave" \
    '[ "$(tr "\n" " " < "$WORK_DIR/log/trace.log")" = "ENTER EXIT ENTER EXIT " ]' \
    "trace=[$(tr '\n' ' ' < "$WORK_DIR/log/trace.log")]"

# The cross case: one domain on DNS-01 and another on HTTP-01 is a supported
# configuration, and both scripts drive the same acme.sh account and state
# directory. Sharing one lock is what keeps that safe.
new_fixture 0 2
(run_issue vdi.example.com) &
FIRST=$!
sleep 0.4
(
    env PATH="$BIN_DIR:/usr/bin:/bin" ACME_HOME="$ACME_HOME_DIR" \
        ACME_CERTS_DIR="$CERTS_DIR" ACME_SERVER=letsencrypt \
        timeout 30 sh "$HTTP01_SCRIPT" http01.example.com http01.pem >/dev/null 2>&1
) &
SECOND=$!
wait $FIRST $SECOND
check "a dns-01 and an http-01 issuance do not interleave either" \
    '[ "$(tr "\n" " " < "$WORK_DIR/log/trace.log")" = "ENTER EXIT ENTER EXIT " ]' \
    "trace=[$(tr '\n' ' ' < "$WORK_DIR/log/trace.log")]"
check "both scripts take the same lock" '[ -f "$(lock_file)" ]' "home=$(ls -a "$ACME_HOME_DIR")"

#-------------------------------------------------------------------------------

echo
echo "1..$TESTS"
if [ "$FAILURES" -eq 0 ]; then
    echo "PASSED: all $TESTS checks"
    exit 0
fi
echo "FAILED: $FAILURES of $TESTS checks"
exit 1
