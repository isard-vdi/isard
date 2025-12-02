#!/bin/bash

# OVS Security Configuration - Always log for audit trail
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] OVS Hypervisor setup starting"

# Determine API access based on deployment scenario
if [ -n "${API_DOMAIN:-}" ]; then
    # Distributed deployment detected via API_DOMAIN
    API_ACCESS="${API_DOMAIN}"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Using API_DOMAIN for access: ${API_ACCESS}"
else
    # All-in-one deployment: resolve isard-api service to IP
    API_ACCESS=$(getent hosts isard-api | awk '{print $1}' | head -1)
    if [ -z "$API_ACCESS" ]; then
        # Fallback to container IP if resolution fails
        API_ACCESS="172.31.255.10"
        echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Could not resolve isard-api, using fallback IP: ${API_ACCESS}"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Resolved isard-api service to IP: ${API_ACCESS}"
    fi
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Final allowed remote access: ${API_ACCESS}"

# Build ovsdb-server command with security considerations
OVSDB_CMD="ovsdb-server --detach --remote=punix:/var/run/openvswitch/db.sock --pidfile=ovsdb-server.pid"

# Add TCP remote access for the determined API access
OVSDB_CMD="$OVSDB_CMD --remote=ptcp:6640:$API_ACCESS"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Adding TCP remote access for: $API_ACCESS"

# Execute the ovsdb-server command
$OVSDB_CMD >/tmp/ovsdb-server.out 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] ovsdb-server started with restricted access"

ovs-vswitchd --detach --verbose --pidfile >/tmp/ovs-vswitchd.out 2>&1
ovs-vsctl add-br ovsbr0
ovs-vsctl set bridge ovsbr0 protocols=OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13
ip link set ovsbr0 up

ovs-vsctl add-port ovsbr0 $DOMAIN -- set interface $DOMAIN type=geneve options:remote_ip=10.1.0.1

# ============================================================================
# SECURITY: RSTP for Loop Protection
# ============================================================================
# Enable RSTP to detect and block L2 loops (e.g., VMs bridging multiple VLANs)
# Combined with BPDU Guard (priority 250 in qemu hook), this prevents:
# - Loops from VMs creating bridges between networks
# - VMs manipulating spanning tree topology
ovs-vsctl set Bridge ovsbr0 rstp_enable=true
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] RSTP enabled for loop protection"

if [ -z ${HYPERVISOR_HOST_TRUNK_INTERFACE+x} ];
then
    echo "No vlan interface set in isardvdi.cfg";
else
    echo "Setting vlan interface: '$HYPERVISOR_HOST_TRUNK_INTERFACE'";
    ovs-vsctl add-port ovsbr0 $HYPERVISOR_HOST_TRUNK_INTERFACE
fi

ovs-vsctl show

# Allow ARP broadcasts from infrastructure services (priority > 210 multicast block)
ovs-ofctl add-flow ovsbr0 "priority=212,arp,dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=10.2.0.1,actions=strip_vlan,output:all"  # gw
ovs-ofctl add-flow ovsbr0 "priority=212,arp,dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=10.2.0.2,actions=strip_vlan,output:all"  # bastion
ovs-ofctl add-flow ovsbr0 "priority=212,arp,dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=10.2.0.3,actions=strip_vlan,output:all"  # samba
ovs-ofctl add-flow ovsbr0 "priority=212,arp,dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=10.2.0.4,actions=strip_vlan,output:all"  # guacamole

# ============================================================================
# SECURITY: Port Security Rules for VLAN 4095 (Infrastructure Network)
# ============================================================================
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Adding port security rules for VLAN 4095"

# Get geneve port number (VPN tunnel) - it's the $DOMAIN port added above
# Port name is the $DOMAIN variable (e.g., "10.100.1.214")
GENEVE_PORT=$(ovs-vsctl get Interface "$DOMAIN" ofport)
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Geneve port to VPN: ${GENEVE_PORT} ($DOMAIN)"

# Allow VLAN 4095 traffic FROM VPN (infrastructure + return traffic)
# This must be higher priority than spoofing blocks below
# Traffic from guests arrives on vnetX ports, not geneve, so they can't bypass
ovs-ofctl add-flow ovsbr0 "priority=211,in_port=${GENEVE_PORT},dl_vlan=4095,actions=NORMAL"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Allowed VLAN 4095 traffic from VPN (port ${GENEVE_PORT})"

# IP Spoofing Protection - Block VLAN 4095 guest traffic claiming protected IPs
# Only affects traffic from VM ports (vnetX), not from geneve (allowed above)
ovs-ofctl add-flow ovsbr0 "priority=210,arp,dl_vlan=4095,arp_spa=10.2.0.0/28,actions=drop"   # Block claiming infra /28
ovs-ofctl add-flow ovsbr0 "priority=210,arp,dl_vlan=4095,arp_spa=10.0.0.0/16,actions=drop"   # Block claiming WG users
ovs-ofctl add-flow ovsbr0 "priority=210,arp,dl_vlan=4095,arp_spa=10.1.0.0/24,actions=drop"   # Block claiming WG hypers

# Multicast Source MAC Blocking - Block VLAN 4095 traffic with multicast source
# Multicast bit = LSB of first octet set (01:xx:xx:xx:xx:xx)
ovs-ofctl add-flow ovsbr0 "priority=210,dl_vlan=4095,dl_src=01:00:00:00:00:00/01:00:00:00:00:00,actions=drop"

# IP Packet Spoofing Protection - Block VLAN 4095 traffic with spoofed source IPs
# (Complements ARP spoofing protection above)
ovs-ofctl add-flow ovsbr0 "priority=210,ip,dl_vlan=4095,nw_src=10.2.0.0/28,actions=drop"   # Block claiming infra /28
ovs-ofctl add-flow ovsbr0 "priority=210,ip,dl_vlan=4095,nw_src=10.0.0.0/16,actions=drop"   # Block claiming WG users
ovs-ofctl add-flow ovsbr0 "priority=210,ip,dl_vlan=4095,nw_src=10.1.0.0/24,actions=drop"   # Block claiming WG hypers

# Block VLAN 4095 guests from reaching Docker network and hypervisor
# More secure than iptables - blocks at L2 before reaching kernel network stack
# DOCKER_NET is passed from docker-compose (e.g., 172.31.255)
ovs-ofctl add-flow ovsbr0 "priority=215,ip,dl_vlan=4095,nw_dst=${DOCKER_NET}.0/24,actions=drop"
ovs-ofctl add-flow ovsbr0 "priority=215,arp,dl_vlan=4095,arp_tpa=${DOCKER_NET}.0/24,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Blocked VLAN 4095 access to Docker network ${DOCKER_NET}.0/24"

# ============================================================================
# SECURITY: Rogue DHCP Server Protection (VLAN 4095 only)
# ============================================================================
# Only allow DHCP server responses from legitimate gateway (10.2.0.1)
ovs-ofctl add-flow ovsbr0 "priority=220,udp,dl_vlan=4095,tp_src=67,nw_src=10.2.0.1,actions=NORMAL"
# Drop all other DHCP server traffic from VLAN 4095
ovs-ofctl add-flow ovsbr0 "priority=219,udp,dl_vlan=4095,tp_src=67,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Rogue DHCP protection enabled for VLAN 4095"

# ============================================================================
# SECURITY: IPv6 Protection for VLAN 4095
# ============================================================================
# Drop all IPv6 traffic from VLAN 4095 (EtherType 0x86DD)
# This blocks all IPv6 including ICMPv6 Router Advertisements (RA Guard)
ovs-ofctl add-flow ovsbr0 "priority=210,dl_vlan=4095,dl_type=0x86dd,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] IPv6 + RA Guard enabled for VLAN 4095"

# ============================================================================
# SECURITY: DNS Spoofing Protection for VLAN 4095
# ============================================================================
# Block DNS responses from guests (no internal DNS server on VLAN 4095)
ovs-ofctl add-flow ovsbr0 "priority=210,udp,dl_vlan=4095,tp_src=53,actions=drop"
ovs-ofctl add-flow ovsbr0 "priority=210,tcp,dl_vlan=4095,tp_src=53,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] DNS spoofing protection enabled for VLAN 4095"

# ============================================================================
# SECURITY: Multicast Destination Blocking for VLAN 4095
# ============================================================================
# Block all multicast destination traffic (no multicast needed on VLAN 4095)
ovs-ofctl add-flow ovsbr0 "priority=210,dl_vlan=4095,dl_dst=01:00:00:00:00:00/01:00:00:00:00:00,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Multicast destination blocking enabled for VLAN 4095"

# ============================================================================
# SECURITY: ARP Rate Limiting Meter for VLAN 4095 (used by qemu hook)
# ============================================================================
# Create meter for per-VM ARP rate limiting (1 pkt/sec sustained, burst of 10)
# This meter is used by qemu hook rules for VLAN 4095 guest ports
ovs-ofctl -O OpenFlow13 add-meter ovsbr0 meter=2,pktps,burst,band=type=drop,rate=1,burst_size=10
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] ARP rate limiting meter created (meter=2, 1 pkt/sec, burst=10)"

# ip a f eth0
#ovs-vsctl add-port ovsbr0 eth0
# ovs-vsctl add-port ovsbr0 eth0 tag=1 vlan_mode=native-tagged

# ip a a 172.31.255.17/24 dev ovsbr0
# ip r a default via 172.31.255.1 dev ovsbr0

# ovs-vsctl set bridge ovsbr0 protocols=OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13
# ovs-vsctl set-controller ovsbr0 tcp:172.31.255.99:6653

# ovs-vsctl add-port ovsbr0 vxlan0 -- set interface vxlan0 type=vxlan options:remote_ip=<REMOTE_IP>
