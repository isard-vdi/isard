#!/bin/sh
# DHCP hook for VLAN 4095 (WireGuard guest network)
# Args: $1=action (add|old|del), $2=MAC, $3=IP, $4=hostname

ACTION=$1
MAC=$2
IP=$3
QUEUE=${DHCP_REPORTS_DIR:-/run/isard-dhcp-reports}

# Static ARP entries for ARP cache poisoning protection
# Static entries cannot be overwritten by ARP replies
case "$ACTION" in
    add|old)
        arp -s "$IP" "$MAC" dev vlan-wg 2>/dev/null || true
        # Source IP pinning: only allow this MAC with this IP on VLAN 4095
        ovs-ofctl add-flow ovsbr0 "table=2,priority=100,ip,dl_src=$MAC,nw_src=$IP,actions=NORMAL"
        # OVS 4.0 keeps the non-RSTP internal port out of the flood, so NORMAL
        # loses these frames once the gateway MAC ages out.
        GW_MAC=$(ip -o link show vlan-wg 2>/dev/null | sed -n 's/.*link\/ether \([0-9a-f:]*\).*/\1/p')
        if [ -n "$GW_MAC" ]; then
            ovs-ofctl add-flow ovsbr0 "table=2,priority=110,ip,dl_src=$MAC,nw_src=$IP,dl_dst=$GW_MAC,actions=strip_vlan,output:vlan-wg"
        fi
        # dnsmasq runs one hook at a time, so the API report is queued for
        # isardvdi-vpn-admin (isardvdi_vpn.dhcp_reports) instead of made here
        mkdir -p "$QUEUE"
        read -r UPTIME _ < /proc/uptime
        PRIO=1
        [ "$ACTION" = add ] && PRIO=0
        NAME="$PRIO.$(printf '%012d' "${UPTIME%.*}${UPTIME#*.}").$$.$ACTION.$(echo "$MAC" | tr : -).$IP"
        : > "$QUEUE/.$NAME" && mv "$QUEUE/.$NAME" "$QUEUE/$NAME"
        ;;
    del)
        arp -d "$IP" dev vlan-wg 2>/dev/null || true
        # Table 2 flow is NOT removed here — managed by wgadmin domain
        # lifecycle instead. Removing on lease expiry breaks running VMs.
        ;;
esac
