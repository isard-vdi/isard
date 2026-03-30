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
        API_ACCESS="${DOCKER_NET:-172.31.255}.10"
        echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Could not resolve isard-api, using fallback IP: ${API_ACCESS}"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Resolved isard-api service to IP: ${API_ACCESS}"
    fi
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Final allowed remote access: ${API_ACCESS}"

# Compute guest infrastructure IPs from WG_GUESTS_NETS
eval $(python3 -c "
import ipaddress, os
gn = ipaddress.ip_network(os.environ.get('WG_GUESTS_NETS', '10.2.0.0/16'), strict=False)
hn = ipaddress.ip_network(os.environ.get('WG_HYPERS_NET', '10.1.0.0/24'), strict=False)
print(f'GUESTS_GW={gn[1]}')
print(f'GUESTS_BASTION={gn[2]}')
print(f'GUESTS_SAMBA={gn[3]}')
print(f'GUESTS_GUAC={gn[4]}')
print(f'GUESTS_INFRA_CIDR={ipaddress.ip_network(str(gn.network_address) + \"/28\", strict=False)}')
print(f'WG_HYPERS_GW={hn[1]}')
" 2>/dev/null) || {
  # Fallback: shell-based extraction for containers without python3
  _NET_BASE=$(echo "${WG_GUESTS_NETS:-10.2.0.0/16}" | cut -d/ -f1)
  _PREFIX=${_NET_BASE%.*}
  GUESTS_GW="${_PREFIX}.1"
  GUESTS_BASTION="${_PREFIX}.2"
  GUESTS_SAMBA="${_PREFIX}.3"
  GUESTS_GUAC="${_PREFIX}.4"
  GUESTS_INFRA_CIDR="${_NET_BASE}/28"
  _HYPERS_BASE=$(echo "${WG_HYPERS_NET:-10.1.0.0/24}" | cut -d/ -f1)
  _HYPERS_PREFIX=${_HYPERS_BASE%.*}
  WG_HYPERS_GW="${_HYPERS_PREFIX}.1"
}

# Ensure OVS DB exists and matches the installed schema version
OVS_DB=/etc/openvswitch/conf.db
OVS_SCHEMA=/usr/share/openvswitch/vswitch.ovsschema
mkdir -p /etc/openvswitch /var/run/openvswitch

if [ ! -f "$OVS_DB" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') [OVS] Creating new OVS database"
    ovsdb-tool create "$OVS_DB" "$OVS_SCHEMA"
elif [ "$(ovsdb-tool needs-conversion "$OVS_DB" "$OVS_SCHEMA" 2>/dev/null)" = "yes" ]; then
    _old=$(ovsdb-tool db-version "$OVS_DB" 2>/dev/null)
    _new=$(ovsdb-tool schema-version "$OVS_SCHEMA" 2>/dev/null)
    echo "$(date '+%Y-%m-%d %H:%M:%S') [OVS] Converting database schema ${_old} -> ${_new}"
    ovsdb-tool convert "$OVS_DB" "$OVS_SCHEMA" || {
        echo "$(date '+%Y-%m-%d %H:%M:%S') [OVS] Conversion failed, recreating database"
        rm -f "$OVS_DB" "$OVS_DB.~lock~"
        ovsdb-tool create "$OVS_DB" "$OVS_SCHEMA"
    }
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') [OVS] Database schema is up to date ($(ovsdb-tool db-version "$OVS_DB"))"
fi

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
# ============================================================================
# PERFORMANCE: OVS Datapath Tuning
# ============================================================================
# Increase handler threads for better tunnel/VM traffic processing
ovs-vsctl set Open_vSwitch . other_config:n-handler-threads=4
# Increase revalidator threads for faster flow updates with many VMs
ovs-vsctl set Open_vSwitch . other_config:n-revalidator-threads=4
echo "$(date '+%Y-%m-%d %H:%M:%S') [PERFORMANCE] OVS datapath tuning applied (4 handler + 4 revalidator threads)"
ovs-vsctl set bridge ovsbr0 protocols=OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13,OpenFlow14
ovs-vsctl set bridge ovsbr0 other_config:mac-table-size=8192
ip link set ovsbr0 up

# Clean up stale tunnel ports from previous tunneling mode.
# The OVS DB persists across container restarts (docker restart doesn't
# recreate the writable layer), so ports from the other mode linger.
# Remove all geneve ports so the mode-specific code below starts fresh.
for _port in $(ovs-vsctl list-ports ovsbr0 2>/dev/null); do
    _ptype=$(ovs-vsctl get interface "$_port" type 2>/dev/null || true)
    if [ "$_ptype" = "geneve" ] || [ "$_ptype" = '"geneve"' ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') [OVS] Removing stale geneve port: $_port"
        ovs-vsctl --if-exists del-port ovsbr0 "$_port"
    fi
done

# Set OVS bridge MTU from central infrastructure config (not local env)
vpn_tunneling_mode=${HYPERVISOR_VPN_TUNNELING_MODE:-wireguard+geneve}

if [ "$vpn_tunneling_mode" = "geneve" ]; then
    # geneve-only: read INFRASTRUCTURE_MTU saved during API registration
    if [ -f /tmp/infrastructure_mtu ]; then
        _ovs_mtu=$(cat /tmp/infrastructure_mtu)
    else
        _ovs_mtu=9000
    fi
else
    # wg+geneve: OVS MTU = WG interface MTU (set by central API config)
    _ovs_mtu=$(ip link show wg0 2>/dev/null | sed -n 's/.*mtu \([0-9]*\).*/\1/p' | head -1)
    [ -z "$_ovs_mtu" ] && _ovs_mtu=1440
fi
ovs-vsctl set interface ovsbr0 mtu_request=$_ovs_mtu
echo "$(date '+%Y-%m-%d %H:%M:%S') [MTU] OVS bridge MTU set to $_ovs_mtu"

if [ "$vpn_tunneling_mode" = "geneve" ]; then
    echo "Configuring OVS for plain Geneve tunneling"
    VPN_DOMAIN=${VPN_DOMAIN:-isard-vpn}
    # OVS remote_ip requires an IP address, not hostname - resolve if needed
    if echo "$VPN_DOMAIN" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
        VPN_REMOTE_IP="$VPN_DOMAIN"
    else
        VPN_REMOTE_IP=$(getent hosts "$VPN_DOMAIN" | awk '{print $1}' | head -1)
        if [ -z "$VPN_REMOTE_IP" ]; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] Cannot resolve VPN_DOMAIN '$VPN_DOMAIN' to IP address"
            exit 1
        fi
    fi
    GENEVE_DST_PORT=${WG_HYPERS_PORT:-4443}
    ovs-vsctl add-port ovsbr0 vpn-geneve -- set interface vpn-geneve \
        type=geneve options:remote_ip=$VPN_REMOTE_IP \
        options:dst_port=$GENEVE_DST_PORT
    ovs-vsctl set Interface vpn-geneve bfd:enable=true bfd:min_tx=1000 bfd:min_rx=1000

    # Wait for BFD tunnel to come up
    echo "Waiting for GENEVE tunnel BFD..."
    for i in $(seq 1 30); do
        BFD_STATE=$(ovs-vsctl get Interface vpn-geneve bfd_status:state 2>/dev/null || echo "init")
        if [ "$BFD_STATE" = '"up"' ]; then echo "BFD tunnel UP"; break; fi
        sleep 2
    done

    GENEVE_PORT=$(ovs-vsctl get Interface vpn-geneve ofport)
else
    echo "Configuring OVS for WireGuard + Geneve tunneling"
    ovs-vsctl add-port ovsbr0 $DOMAIN -- set interface $DOMAIN type=geneve options:remote_ip=$WG_HYPERS_GW
    echo "$(date '+%Y-%m-%d %H:%M:%S') [OVS] Geneve tunnel to VPN gateway $WG_HYPERS_GW (from WG_HYPERS_NET)"
    GENEVE_PORT=$(ovs-vsctl get Interface "$DOMAIN" ofport)
fi

# Save computed gateway for reuse by start.sh keepalive loop
echo "$WG_HYPERS_GW" > /tmp/wg_hypers_gw

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

# ============================================================================
# SECURITY: Port Security Rules for VLAN 4095 (Infrastructure Network)
# ============================================================================
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Adding port security rules for VLAN 4095"

# GENEVE_PORT already set above based on tunneling mode
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Geneve port to VPN: ${GENEVE_PORT}"

# Allow ARP broadcasts from infrastructure services (priority > 210 multicast block)
# Restricted to geneve ingress to prevent VMs from spoofing infrastructure ARP
ovs-ofctl add-flow ovsbr0 "priority=212,arp,in_port=${GENEVE_PORT},dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=${GUESTS_GW},actions=strip_vlan,output:all"  # gw
ovs-ofctl add-flow ovsbr0 "priority=212,arp,in_port=${GENEVE_PORT},dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=${GUESTS_BASTION},actions=strip_vlan,output:all"  # bastion
ovs-ofctl add-flow ovsbr0 "priority=212,arp,in_port=${GENEVE_PORT},dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=${GUESTS_SAMBA},actions=strip_vlan,output:all"  # samba
ovs-ofctl add-flow ovsbr0 "priority=212,arp,in_port=${GENEVE_PORT},dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=${GUESTS_GUAC},actions=strip_vlan,output:all"  # guacamole

# Allow VLAN 4095 traffic FROM VPN (infrastructure + return traffic)
# This must be higher priority than spoofing blocks below
# Traffic from guests arrives on vnetX ports, not geneve, so they can't bypass
ovs-ofctl add-flow ovsbr0 "priority=211,in_port=${GENEVE_PORT},dl_vlan=4095,actions=NORMAL"
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] Allowed VLAN 4095 traffic from VPN (port ${GENEVE_PORT})"

# IP Spoofing Protection - Block VLAN 4095 guest traffic claiming protected IPs
# Only affects traffic from VM ports (vnetX), not from geneve (allowed above)
ovs-ofctl add-flow ovsbr0 "priority=210,arp,dl_vlan=4095,arp_spa=${GUESTS_INFRA_CIDR},actions=drop"   # Block claiming infra
ovs-ofctl add-flow ovsbr0 "priority=210,arp,dl_vlan=4095,arp_spa=${WG_USERS_NET},actions=drop"   # Block claiming WG users
ovs-ofctl add-flow ovsbr0 "priority=210,arp,dl_vlan=4095,arp_spa=${WG_HYPERS_NET},actions=drop"   # Block claiming WG hypers

# Multicast Source MAC Blocking - Block VLAN 4095 traffic with multicast source
# Multicast bit = LSB of first octet set (01:xx:xx:xx:xx:xx)
ovs-ofctl add-flow ovsbr0 "priority=210,dl_vlan=4095,dl_src=01:00:00:00:00:00/01:00:00:00:00:00,actions=drop"

# IP Packet Spoofing Protection - Block VLAN 4095 traffic with spoofed source IPs
# (Complements ARP spoofing protection above)
ovs-ofctl add-flow ovsbr0 "priority=210,ip,dl_vlan=4095,nw_src=${GUESTS_INFRA_CIDR},actions=drop"   # Block claiming infra
ovs-ofctl add-flow ovsbr0 "priority=210,ip,dl_vlan=4095,nw_src=${WG_USERS_NET},actions=drop"   # Block claiming WG users
ovs-ofctl add-flow ovsbr0 "priority=210,ip,dl_vlan=4095,nw_src=${WG_HYPERS_NET},actions=drop"   # Block claiming WG hypers

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
ovs-ofctl add-flow ovsbr0 "priority=220,udp,in_port=${GENEVE_PORT},dl_vlan=4095,tp_src=67,nw_src=${GUESTS_GW},actions=NORMAL"
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

# ip a f eth0
#ovs-vsctl add-port ovsbr0 eth0
# ovs-vsctl add-port ovsbr0 eth0 tag=1 vlan_mode=native-tagged

# ip a a ${DOCKER_NET:-172.31.255}.17/24 dev ovsbr0
# ip r a default via ${DOCKER_NET:-172.31.255}.1 dev ovsbr0

