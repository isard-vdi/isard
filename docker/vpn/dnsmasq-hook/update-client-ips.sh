#!/bin/sh
# DHCP hook for VLAN 4095 (WireGuard guest network)
# Args: $1=action (add|old|del), $2=MAC, $3=IP, $4=hostname

ACTION=$1
MAC=$2
IP=$3

export API_HYPERVISORS_SECRET=$API_HYPERVISORS_SECRET

# Notify API of IP assignment (existing functionality).
# Use the venv interpreter: python:3.13-alpine has no /usr/bin/python3, and isardvdi_apiv4_client only lives in the venv.
/.venv/bin/python3 /dnsmasq-hook/update-client-ips.py "$@"

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
        ;;
    del)
        arp -d "$IP" dev vlan-wg 2>/dev/null || true
        # Table 2 flow is NOT removed here — managed by wgadmin domain
        # lifecycle instead. Removing on lease expiry breaks running VMs.
        ;;
esac
