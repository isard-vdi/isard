#!/bin/bash

# OVS Security Configuration - Always log for audit trail
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] OVS VPN setup starting"

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

echo "$(date '+%Y-%m-%d %H:%M:%S') INFO: Starting OpenVSWitch server"

# Build ovsdb-server command with security considerations
OVSDB_CMD="ovsdb-server --detach --remote=punix:/var/run/openvswitch/db.sock --pidfile=ovsdb-server.pid"

# Add TCP remote access for the determined API access
OVSDB_CMD="$OVSDB_CMD --remote=ptcp:6640:$API_ACCESS"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Adding TCP remote access for: $API_ACCESS"

# Execute the ovsdb-server command
$OVSDB_CMD > /var/log/ovs 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] ovsdb-server started with restricted access"

ovs-vswitchd --detach --verbose --pidfile  >> /var/log/ovs 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') INFO: Adding OVS default bridge"
ovs-vsctl add-br ovsbr0 >> /var/log/ovs 2>&1
ovs-vsctl set bridge ovsbr0 protocols=OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13 >> /var/log/ovs 2>&1
ip link set ovsbr0 up >> /var/log/ovs 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') INFO: Adding OVS vlan-wg port to default bridge with tag 4095"
ovs-vsctl add-port ovsbr0 vlan-wg tag=4095 -- set interface vlan-wg type=internal >> /var/log/ovs 2>&1
ip a a 10.2.0.1/16 dev vlan-wg >> /var/log/ovs 2>&1
ip link set vlan-wg up >> /var/log/ovs 2>&1

# Monitor if vlan-wg is really up
while ! ip a s vlan-wg; do
  echo "$(date '+%Y-%m-%d %H:%M:%S') INFO: Waiting for vlan-wg to be up..."
  sleep 1
done

# ============================================================================
# SECURITY: RSTP for Loop Protection
# ============================================================================
# Enable RSTP to detect and block L2 loops (e.g., trunk added to multiple containers via pipework)
# Both VPN and Hypervisor OVS bridges need RSTP for cross-container loop detection
ovs-vsctl set Bridge ovsbr0 rstp_enable=true
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] RSTP enabled for loop protection"

# Table 2: source IP pinning for VM traffic (populated by dnsmasq hook)
# Default: drop unpinned source IPs
ovs-ofctl add-flow ovsbr0 "table=2,priority=0,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Table 2 default drop for unpinned VM IPs"

# Bastion port (geneve tunnel to bastion container)
ovs-vsctl add-port ovsbr0 bastion -- set interface bastion type=geneve options:remote_ip=172.31.255.117 >> /var/log/ovs 2>&1

# Samba port (geneve tunnel to samba container)
ovs-vsctl add-port ovsbr0 samba -- set interface samba type=geneve options:remote_ip=172.31.255.100 >> /var/log/ovs 2>&1

# Get port numbers for bastion and samba
BASTION_PORT=$(ovs-vsctl get Interface bastion ofport 2>/dev/null)
SAMBA_PORT=$(ovs-vsctl get Interface samba ofport 2>/dev/null)

# Get vlan-wg port number for VPN gateway
VLAN_WG_PORT=$(ovs-vsctl get Interface vlan-wg ofport 2>/dev/null)

# Allow traffic FROM infrastructure ports at higher priority than spoofing blocks (p410)
# This ensures bastion, samba, and VPN gateway can communicate while still blocking
# spoofed traffic from hypervisor ports
if [ -n "$BASTION_PORT" ] && [ "$BASTION_PORT" != "-1" ]; then
    ovs-ofctl add-flow ovsbr0 "priority=420,in_port=${BASTION_PORT},dl_vlan=4095,actions=NORMAL"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Added bastion VLAN 4095 flow rule (port ${BASTION_PORT}, priority 420)"
fi
if [ -n "$SAMBA_PORT" ] && [ "$SAMBA_PORT" != "-1" ]; then
    ovs-ofctl add-flow ovsbr0 "priority=420,in_port=${SAMBA_PORT},dl_vlan=4095,actions=NORMAL"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Added samba VLAN 4095 flow rule (port ${SAMBA_PORT}, priority 420)"
fi
if [ -n "$VLAN_WG_PORT" ] && [ "$VLAN_WG_PORT" != "-1" ]; then
    ovs-ofctl add-flow ovsbr0 "priority=420,in_port=${VLAN_WG_PORT},dl_vlan=4095,actions=NORMAL"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Added VPN gateway VLAN 4095 flow rule (port ${VLAN_WG_PORT}, priority 420)"
fi

# ============================================================================
# SECURITY: VLAN 4095 Filtering at VPN
# ============================================================================
# Block STP/BPDU frames globally (prevent spanning tree manipulation)
ovs-ofctl add-flow ovsbr0 "priority=500,dl_dst=01:80:c2:00:00:00,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Blocked STP/BPDU frames"

# Block IPv6 on VLAN 4095 (no IPv6 on infrastructure network)
ovs-ofctl add-flow ovsbr0 "priority=400,dl_vlan=4095,dl_type=0x86dd,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Blocked IPv6 on VLAN 4095"

# Block multicast destination on VLAN 4095 (no multicast needed)
ovs-ofctl add-flow ovsbr0 "priority=400,dl_vlan=4095,dl_dst=01:00:00:00:00:00/01:00:00:00:00:00,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Blocked multicast on VLAN 4095"

# Allow broadcast from VPN gateway (vlan-wg), block from others
VLAN_WG_MAC=$(ip link show vlan-wg 2>/dev/null | grep ether | awk '{print $2}')
if [ -n "$VLAN_WG_MAC" ]; then
    ovs-ofctl add-flow ovsbr0 "priority=402,dl_vlan=4095,dl_src=${VLAN_WG_MAC},dl_dst=ff:ff:ff:ff:ff:ff,actions=NORMAL"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Allowed broadcasts from VPN gateway ($VLAN_WG_MAC)"
fi
# Allow DHCP requests from guests (UDP 68→67, broadcast) before blocking other broadcasts
ovs-ofctl add-flow ovsbr0 "priority=401,udp,dl_vlan=4095,tp_src=68,tp_dst=67,dl_dst=ff:ff:ff:ff:ff:ff,actions=NORMAL"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Allowed DHCP requests on VLAN 4095"
ovs-ofctl add-flow ovsbr0 "priority=400,dl_vlan=4095,dl_dst=ff:ff:ff:ff:ff:ff,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Blocked broadcasts on VLAN 4095 (except VPN gateway and DHCP)"

# ============================================================================
# SECURITY: ARP Spoofing Protection for VLAN 4095 (defense-in-depth)
# ============================================================================
# Block ARP packets claiming infrastructure IPs (10.2.0.0/28 = .1-.15)
ovs-ofctl add-flow ovsbr0 "priority=410,arp,dl_vlan=4095,arp_spa=10.2.0.0/28,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Blocked ARP spoofing for infra IPs (10.2.0.0/28)"

# Block ARP packets claiming WireGuard user IPs
ovs-ofctl add-flow ovsbr0 "priority=410,arp,dl_vlan=4095,arp_spa=10.0.0.0/16,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Blocked ARP spoofing for WG user IPs (10.0.0.0/16)"

# Block ARP packets claiming WireGuard hypervisor IPs
ovs-ofctl add-flow ovsbr0 "priority=410,arp,dl_vlan=4095,arp_spa=10.1.0.0/24,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Blocked ARP spoofing for WG hyper IPs (10.1.0.0/24)"

# Block IP packets with spoofed source IPs (complements ARP protection)
ovs-ofctl add-flow ovsbr0 "priority=410,ip,dl_vlan=4095,nw_src=10.2.0.0/28,actions=drop"
ovs-ofctl add-flow ovsbr0 "priority=410,ip,dl_vlan=4095,nw_src=10.0.0.0/16,actions=drop"
ovs-ofctl add-flow ovsbr0 "priority=410,ip,dl_vlan=4095,nw_src=10.1.0.0/24,actions=drop"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Blocked IP spoofing for protected ranges"

# Handle trunk interface mapping (similar to hypervisor)
if [ -z ${HYPERVISOR_HOST_TRUNK_INTERFACE+x} ];
then
    echo "$(date '+%Y-%m-%d %H:%M:%S') INFO: No VPN trunk interface set in isardvdi.cfg"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') INFO: Setting VPN trunk interface: '$HYPERVISOR_HOST_TRUNK_INTERFACE'"
    ovs-vsctl add-port ovsbr0 $HYPERVISOR_HOST_TRUNK_INTERFACE
    echo "$(date '+%Y-%m-%d %H:%M:%S') INFO: VPN trunk interface $HYPERVISOR_HOST_TRUNK_INTERFACE added to OVS bridge"
fi

mkdir -p /var/run/dnsmasq
mkdir -p /var/lib/dnsmasq
cat <<EOT > /etc/dnsmasq.d/vlan-wg.conf
strict-order
port=0
pid-file=/var/run/ovs-vlan-wg.pid
except-interface=lo
bind-dynamic
interface=vlan-wg
dhcp-range=10.2.0.16,10.2.255.254,255.255.0.0
dhcp-no-override
dhcp-authoritative
dhcp-lease-max=100000
#dhcp-hostsfile=/var/lib/misc/vlan-wg.static_leases
dhcp-hostsdir=/var/lib/static_leases
dhcp-option=121,10.0.0.0/14,10.2.0.1
dhcp-option=26,1366
#dhcp-option=vlan-wg,3,10.2.0.1
dhcp-script=/dnsmasq-hook/update-client-ips.sh
dhcp-leasefile=/var/lib/misc/vlan-wg.leases
dhcp-option=3
dhcp-ignore-names
dhcp-ignore-clid
EOT

if [ ! -f /var/lib/static_leases/SAMPLE ]
then
cat <<EOT > /var/lib/static_leases/SAMPLE
# Static DHCP Wireguard leases
## Does not need isard-vpn restart if guest yet doesn't have ip on vlan-wg.leases
## NOTE: If MAC it's already on vlan-wg.leases you must stop desktop, delete entry, restart isard-vpn
## One file for each host in this format:
## <MAC>,<IP>,<NETWORK NAME>,<LEASE_TIME>
## Example: 00:11:22:33:44:55,192.168.255.2,nas,24h
EOT
fi

if [ ! -f /var/lib/misc/README ]
then
cat <<EOT > /var/lib/misc/README
# Do not edit vlan-wg.leases file while isard-vpn is started, its not autoreloaded
## If you really need to do that stop isard-vpn before doing it.
## Your static dhcp assignment files should go at static_leases folder
EOT
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') INFO: Starting dnsmasq wireguard server"
/usr/sbin/dnsmasq --conf-file=/etc/dnsmasq.d/vlan-wg.conf --dhcp-script=/dnsmasq-hook/update-client-ips.sh >> /var/log/dnsmasq 2>&1 &
