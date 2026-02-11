#!/bin/sh
# DHCP hook for VLAN 4095 (WireGuard guest network)
# Args: $1=action (add|old|del), $2=MAC, $3=IP, $4=hostname

ACTION=$1
MAC=$2
IP=$3

export API_HYPERVISORS_SECRET=$API_HYPERVISORS_SECRET

# Notify API of IP assignment (existing functionality)
/usr/bin/python3 /dnsmasq-hook/update-client-ips.py "$@"

# Static ARP entries for ARP cache poisoning protection
# Static entries cannot be overwritten by ARP replies
case "$ACTION" in
    add|old)
        arp -s "$IP" "$MAC" dev vlan-wg 2>/dev/null || true
        # Source IP pinning: only allow this MAC with this IP on VLAN 4095
        ovs-ofctl add-flow ovsbr0 "table=2,priority=100,ip,dl_src=$MAC,nw_src=$IP,actions=NORMAL"
        ;;
    del)
        arp -d "$IP" dev vlan-wg 2>/dev/null || true
        # Remove source IP pinning
        ovs-ofctl del-flows --strict ovsbr0 "table=2,priority=100,ip,dl_src=$MAC,nw_src=$IP"
        ;;
esac
