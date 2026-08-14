#!/bin/bash
#===============================================================================
# Suite: INFRASTRUCTURE_HOST_IP binding
#===============================================================================
# Two things are asserted here because both used to fail late and unhelpfully:
#
#   1. build.sh's validator. The variable ends up as a published port's bind
#      address, so docker rejects a hostname ("invalid ip address") and an
#      address the host does not hold ("cannot assign requested address") --
#      both at `up`, both naming a port rather than the variable.
#
#   2. The `:?` guard on the *.infrastructure-ports.yml parts. In compose SHORT
#      syntax an empty variable does NOT error: "${VAR}:28015:28015" silently
#      renders as 28015:28015, i.e. RethinkDB published on every interface. The
#      guard is what turns that into a refusal, so a test that only checked the
#      happy path would not notice if someone dropped it.
#
# The validator is read out of build.sh rather than sourced: build.sh runs its
# whole pipeline on source, so there is nothing to source in isolation.
#
# `docker compose` is needed for group 2 only; without it those cases SKIP
# loudly instead of passing vacuously.
#
# Run it with: make test-infrastructure-host-ip
#===============================================================================

set -u -o pipefail

TESTS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$TESTS_DIR/.." && pwd)
BUILD_SH="$ROOT/build.sh"
PARTS="$ROOT/docker-compose-parts"

pass=0; fail=0; skip=0
ok()   { echo "  ok    $1"; pass=$((pass+1)); }
ko()   { echo "  FAIL  $1"; echo "        $2"; fail=$((fail+1)); }
skipt(){ echo "  skip  $1 ($2)"; skip=$((skip+1)); }

#-- the validator, lifted out of build.sh -------------------------------------
VALIDATOR=$(awk '/^validate_infrastructure_host_ip\(\)\{/{p=1} p{print} p&&/^\}/{exit}' "$BUILD_SH")
if [ -z "$VALIDATOR" ]; then
    echo "FATAL: validate_infrastructure_host_ip() not found in $BUILD_SH" >&2
    exit 2
fi

# Returns 0 when the validator accepts the value, 1 when it refuses.
validate() {
    INFRASTRUCTURE_HOST_IP="$1" bash -c "$VALIDATOR
validate_infrastructure_host_ip" >/dev/null 2>&1
}

# The refusal message, so a case can assert WHICH guard caught the value. The
# two guards reject overlapping inputs -- a hostname is also absent from every
# interface -- so a test that only checks "was refused" stays green when the
# format check is deleted.
why() {
    INFRASTRUCTURE_HOST_IP="$1" bash -c "$VALIDATOR
validate_infrastructure_host_ip" 2>&1 >/dev/null
}

echo "== validator =="

# An address this host really holds must be accepted, otherwise every build on
# a correctly configured host would break.
own_ip=$(ip -o -4 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)
if [ -n "$own_ip" ]; then
    if validate "$own_ip"; then ok "accepts an address this host holds ($own_ip)"
    else ko "accepts an address this host holds ($own_ip)" "refused a live local address"; fi
else
    skipt "accepts an address this host holds" "no global IPv4 on this host"
fi

# 127.0.0.1 is held by every host, so this also proves the check reads the
# interface list rather than guessing from the value.
if validate "127.0.0.1"; then ok "accepts 127.0.0.1"
else ko "accepts 127.0.0.1" "refused the loopback address"; fi

# A hostname resolves, so it looks fine until docker rejects it. It must be
# caught as a FORMAT error: it is also absent from every interface, so asserting
# only "was refused" would still pass with the format check deleted.
msg=$(why "isard-web.example.com")
if validate "isard-web.example.com"; then
    ko "refuses a hostname as a format error" "accepted a hostname; docker would fail with 'invalid ip address'"
elif ! echo "$msg" | grep -q 'not a literal IP address'; then
    ko "refuses a hostname as a format error" "refused, but on the wrong guard: $(echo "$msg" | grep -m1 ERROR)"
else ok "refuses a hostname as a format error"; fi

# An unset-but-present variable would sail through a bare [ -n ] test.
msg=$(why "")
if validate ""; then ko "refuses an empty value" "accepted an empty value"
elif ! echo "$msg" | grep -q 'not a literal IP address'; then
    ko "refuses an empty value" "refused, but on the wrong guard: $(echo "$msg" | grep -m1 ERROR)"
else ok "refuses an empty value"; fi

# The floating-VIP case: a well-formed address that this host does not hold, so
# it must be caught by the INTERFACE check and not by the format one.
msg=$(why "203.0.113.253")
if validate "203.0.113.253"; then
    ko "refuses an IP no interface holds" "accepted an absent address; docker would fail with 'cannot assign requested address'"
elif ! echo "$msg" | grep -q 'not on any interface'; then
    ko "refuses an IP no interface holds" "refused, but on the wrong guard: $(echo "$msg" | grep -m1 ERROR)"
else ok "refuses an IP no interface holds"; fi

echo "== parts =="

if ! docker compose version >/dev/null 2>&1; then
    skipt "part rendering" "docker compose unavailable"
else
    # A part file on its own is NOT a valid compose project -- it declares ports
    # for a service whose image lives in the base part -- so it must be chained
    # with that base. Rendering it alone fails with "has neither an image nor a
    # build context", which would make every assertion below pass for the wrong
    # reason.
    # Rendering happens on a throwaway copy of the parts directory: some parts
    # declare `env_file: .env`, which build.sh generates and a source checkout
    # does not have, and creating it in the tree would dirty the working copy.
    WORK=$(mktemp -d)
    trap 'rm -rf "$WORK"' EXIT
    cp "$PARTS"/*.yml "$WORK"/ 2>/dev/null
    : > "$WORK/.env"

    # network.yml is chained too because the service parts attach to
    # isard-network without defining it ("refers to undefined network").
    render() { # <base-basename> <overlay-basename> ; env comes from the caller
        docker compose -f "$WORK/network.yml" -f "$WORK/$1" -f "$WORK/$2" config 2>&1
    }

    # Every infrastructure-ports part must refuse an empty value rather than
    # rendering a 0.0.0.0 publish. The message is asserted too: a failure for
    # any other reason would otherwise read as the guard working.
    for part in "$PARTS"/*.infrastructure-ports.yml; do
        name=$(basename "$part")
        base="${name%.infrastructure-ports.yml}.yml"
        if [ ! -f "$PARTS/$base" ]; then
            ko "$name has a base part" "expected $PARTS/$base"
            continue
        fi
        out=$(INFRASTRUCTURE_HOST_IP="" render "$base" "$name")
        if [ $? -eq 0 ]; then
            ko "$name refuses an empty INFRASTRUCTURE_HOST_IP" "rendered anyway: $(echo "$out" | grep -m1 published || true)"
        elif ! echo "$out" | grep -q 'INFRASTRUCTURE_HOST_IP'; then
            ko "$name refuses an empty INFRASTRUCTURE_HOST_IP" "failed, but not on the guard: $(echo "$out" | tail -1)"
        else
            ok "$name refuses an empty INFRASTRUCTURE_HOST_IP"
        fi
    done

    # The hypervisor part is the one that did not exist: assert both of its
    # ports, because publishing only 2022 registers a host that then carries no
    # desktop traffic.
    hyp="hypervisor.infrastructure-ports.yml"
    hypbase="hypervisor.yml"
    if [ -f "$PARTS/$hyp" ] && [ -f "$PARTS/$hypbase" ]; then
        out=$(INFRASTRUCTURE_HOST_IP="10.11.12.13" WG_HYPERS_PORT="4443" render "$hypbase" "$hyp")
        # host_ip must be the infrastructure address on BOTH entries: a publish
        # that renders without it is the 0.0.0.0 case this part exists to avoid.
        binds=$(echo "$out" | grep -c 'host_ip: 10\.11\.12\.13')
        if [ "$binds" -eq 2 ]; then
            ok "hypervisor part binds both ports to the infrastructure IP"
        else
            ko "hypervisor part binds both ports to the infrastructure IP" "found $binds host_ip lines, expected 2"
        fi
        # compose renders `target:` before `published:`, hence -B and not -A.
        if echo "$out" | grep -B3 'published: "2022"' | grep -q 'target: 2022'; then
            ok "hypervisor part publishes ssh 2022"
        else
            ko "hypervisor part publishes ssh 2022" "$(echo "$out" | grep -A4 ports: | head -12)"
        fi
        if echo "$out" | grep -B2 -A2 'protocol: udp' | grep -q '4443'; then
            ok "hypervisor part publishes the tunnel port as udp"
        else
            ko "hypervisor part publishes the tunnel port as udp" "$(echo "$out" | grep -A12 ports: | head -14)"
        fi
        # WG_HYPERS_PORT is configurable; a hardcoded 4443 would silently ignore it.
        out=$(INFRASTRUCTURE_HOST_IP="10.11.12.13" WG_HYPERS_PORT="5555" render "$hypbase" "$hyp")
        if echo "$out" | grep -q '5555'; then ok "hypervisor part honours WG_HYPERS_PORT"
        else ko "hypervisor part honours WG_HYPERS_PORT" "$(echo "$out" | grep -A12 ports: | head -14)"; fi
    else
        ko "hypervisor part exists" "$PARTS/$hyp or $PARTS/$hypbase is missing"
    fi

    # grafana rides the monitor part: on a monitor-only node the web node's
    # portal proxies /monitor across hosts, so it has to be reachable there.
    mon="monitor.infrastructure-ports.yml"
    if [ -f "$PARTS/$mon" ]; then
        out=$(INFRASTRUCTURE_HOST_IP="10.11.12.13" render "monitor.yml" "$mon")
        for svc in isard-loki isard-victoriametrics isard-grafana; do
            # Slice the service's own block: a fixed -A window is a coin toss,
            # since how far `ports:` sits below the service key depends on how
            # much environment the service declares.
            block=$(echo "$out" | awk -v s="  $svc:" '$0==s{p=1;next} p&&/^  [a-z]/{exit} p')
            if echo "$block" | grep -q 'host_ip: 10\.11\.12\.13'; then
                ok "monitor part binds $svc"
            else
                ko "monitor part binds $svc" "no host_ip in its block"
            fi
        done
    fi

    # The public ports must NOT gain a binding: the viewer ports are announced
    # to the client and the user's browser dials them directly.
    for pair in "video.yml:VIEWER" "portal.yml:portal" "bastion-open-port.yml:bastion"; do
        f="$PARTS/${pair%%:*}"
        [ -f "$f" ] || continue
        if grep -q 'host_ip' "$f"; then
            ko "$(basename "$f") stays unbound" "it gained a host_ip; end users dial these ports directly"
        else
            ok "$(basename "$f") stays unbound"
        fi
    done
fi

echo
echo "passed=$pass failed=$fail skipped=$skip"
[ "$fail" -eq 0 ]
