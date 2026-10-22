#!/bin/sh
# Idempotent geneve-only tunnel port to the VPN plus its ingress flows.
# Usage: geneve-tunnel.sh ensure [wait_s] (exit 1: no VPN address, 2: no ofport) | flows <ofport>

set -u

ACTION=${1:-ensure}
VPN_DOMAIN=${VPN_DOMAIN:-isard-vpn}
GENEVE_DST_PORT=${WG_HYPERS_PORT:-4443}
PORT_NAME=vpn-geneve

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [OVS] $*" >&2; }

eval "$(python3 -c "
import ipaddress, os
gn = ipaddress.ip_network(os.environ.get('WG_GUESTS_NETS', '10.2.0.0/16'), strict=False)
print(f'GUESTS_GW={gn[1]}')
print(f'GUESTS_BASTION={gn[2]}')
print(f'GUESTS_SAMBA={gn[3]}')
print(f'GUESTS_GUAC={gn[4]}')
" 2>/dev/null)" || {
    _prefix=$(echo "${WG_GUESTS_NETS:-10.2.0.0/16}" | cut -d/ -f1)
    _prefix=${_prefix%.*}
    GUESTS_GW="${_prefix}.1"
    GUESTS_BASTION="${_prefix}.2"
    GUESTS_SAMBA="${_prefix}.3"
    GUESTS_GUAC="${_prefix}.4"
}

install_ingress_flows() {
    GENEVE_PORT=$1
    # Above the priority=210 drops: only the tunnel may carry infrastructure ARP, VLAN 4095 and DHCP answers.
    ovs-ofctl add-flow ovsbr0 "priority=212,arp,in_port=${GENEVE_PORT},dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=${GUESTS_GW},actions=strip_vlan,output:all"      # gw
    ovs-ofctl add-flow ovsbr0 "priority=212,arp,in_port=${GENEVE_PORT},dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=${GUESTS_BASTION},actions=strip_vlan,output:all" # bastion
    ovs-ofctl add-flow ovsbr0 "priority=212,arp,in_port=${GENEVE_PORT},dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=${GUESTS_SAMBA},actions=strip_vlan,output:all"   # samba
    ovs-ofctl add-flow ovsbr0 "priority=212,arp,in_port=${GENEVE_PORT},dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=${GUESTS_GUAC},actions=strip_vlan,output:all"    # guacamole
    ovs-ofctl add-flow ovsbr0 "priority=211,in_port=${GENEVE_PORT},dl_vlan=4095,actions=NORMAL"
    ovs-ofctl add-flow ovsbr0 "priority=220,udp,in_port=${GENEVE_PORT},dl_vlan=4095,tp_src=67,nw_src=${GUESTS_GW},actions=NORMAL"
    log "Geneve ingress flows installed on port $GENEVE_PORT"
}

if [ "$ACTION" = "flows" ]; then
    install_ingress_flows "${2:?ofport required}"
    exit 0
fi
[ "$ACTION" = "ensure" ] || { log "[ERROR] unknown action '$ACTION'"; exit 64; }
RESOLVE_WAIT=${2:-0}

resolve_vpn() {
    if echo "$VPN_DOMAIN" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
        echo "$VPN_DOMAIN"
        return 0
    fi
    _deadline=$(($(date +%s) + RESOLVE_WAIT))
    while :; do
        _ip=$(getent hosts "$VPN_DOMAIN" | awk '{print $1}' | head -1)
        if [ -n "$_ip" ]; then
            echo "$_ip"
            return 0
        fi
        [ "$(date +%s)" -ge "$_deadline" ] && return 1
        log "VPN_DOMAIN '$VPN_DOMAIN' does not resolve yet; retrying in 2s"
        sleep 2
    done
}

VPN_REMOTE_IP=$(resolve_vpn) || {
    log "[ERROR] Cannot resolve VPN_DOMAIN '$VPN_DOMAIN' to an IP address"
    exit 1
}

changed=0
if ! ovs-vsctl --if-exists get Interface "$PORT_NAME" type 2>/dev/null | grep -q geneve; then
    ovs-vsctl --may-exist add-port ovsbr0 "$PORT_NAME" -- set interface "$PORT_NAME" \
        type=geneve options:remote_ip="$VPN_REMOTE_IP" \
        options:dst_port="$GENEVE_DST_PORT"
    log "Created $PORT_NAME to $VPN_REMOTE_IP:$GENEVE_DST_PORT"
    changed=1
else
    _current=$(ovs-vsctl get Interface "$PORT_NAME" options:remote_ip 2>/dev/null | tr -d '"')
    if [ "$_current" != "$VPN_REMOTE_IP" ]; then
        ovs-vsctl set Interface "$PORT_NAME" options:remote_ip="$VPN_REMOTE_IP" \
            options:dst_port="$GENEVE_DST_PORT"
        log "Moved $PORT_NAME from '$_current' to $VPN_REMOTE_IP"
        changed=1
    fi
fi

# BFD is the only tunnel liveness signal in geneve-only (vpn.tunnel_status).
ovs-vsctl set Interface "$PORT_NAME" bfd:enable=true bfd:min_tx=200 bfd:min_rx=200

GENEVE_PORT=$(ovs-vsctl get Interface "$PORT_NAME" ofport 2>/dev/null)
case "$GENEVE_PORT" in
    '' | -1 | '[]')
        log "[ERROR] $PORT_NAME has no ofport yet"
        exit 2
        ;;
esac

if [ "$changed" = 0 ] &&
    [ "$(ovs-ofctl dump-flows ovsbr0 "in_port=$GENEVE_PORT,dl_vlan=4095" 2>/dev/null | grep -c 'priority=211')" -gt 0 ]; then
    echo "GENEVE_PORT=$GENEVE_PORT"
    exit 0
fi

install_ingress_flows "$GENEVE_PORT"

echo "GENEVE_PORT=$GENEVE_PORT"
