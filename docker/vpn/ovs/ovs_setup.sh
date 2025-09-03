#!/bin/bash

# OVS Security Configuration - Always log for audit trail
echo "$(date): [SECURITY] OVS VPN setup starting"

# Determine API access based on deployment scenario
if [ -n "${API_DOMAIN:-}" ]; then
    # Distributed deployment detected via API_DOMAIN
    API_ACCESS="${API_DOMAIN}"
    echo "$(date): [SECURITY] Using API_DOMAIN for access: ${API_ACCESS}"
else
    # All-in-one deployment: resolve isard-api service to IP
    API_ACCESS=$(getent hosts isard-api | awk '{print $1}' | head -1)
    if [ -z "$API_ACCESS" ]; then
        # Fallback to container IP if resolution fails
        API_ACCESS="172.31.255.10"
        echo "$(date): [SECURITY] Could not resolve isard-api, using fallback IP: ${API_ACCESS}"
    else
        echo "$(date): [SECURITY] Resolved isard-api service to IP: ${API_ACCESS}"
    fi
fi

echo "$(date): [SECURITY] Final allowed remote access: ${API_ACCESS}"

echo "$(date): INFO: Starting OpenVSWitch server"

# Build ovsdb-server command with security considerations
OVSDB_CMD="ovsdb-server --detach --remote=punix:/var/run/openvswitch/db.sock --pidfile=ovsdb-server.pid"

# Add TCP remote access for the determined API access
OVSDB_CMD="$OVSDB_CMD --remote=ptcp:6640:$API_ACCESS"
echo "$(date): [SECURITY] Adding TCP remote access for: $API_ACCESS"

# Execute the ovsdb-server command
$OVSDB_CMD > /var/log/ovs 2>&1

echo "$(date): [SECURITY] ovsdb-server started with restricted access"

ovs-vswitchd --detach --verbose --pidfile  >> /var/log/ovs 2>&1

echo "$(date): INFO: Adding OVS default bridge"
ovs-vsctl add-br ovsbr0 >> /var/log/ovs 2>&1
ip link set ovsbr0 up >> /var/log/ovs 2>&1

echo "$(date): INFO: Adding OVS vlan-wg port to default bridge with tag 4095"
ovs-vsctl add-port ovsbr0 vlan-wg tag=4095 -- set interface vlan-wg type=internal >> /var/log/ovs 2>&1
ip a a 10.2.0.1/16 dev vlan-wg >> /var/log/ovs 2>&1
ip link set vlan-wg up >> /var/log/ovs 2>&1

# Monitor if vlan-wg is really up
while ! ip a s vlan-wg; do
  echo "$(date): INFO: Waiting for vlan-wg to be up..."
  sleep 1
done

# Bastion port
ovs-vsctl add-port ovsbr0 bastion -- set interface bastion type=geneve options:remote_ip=172.31.255.117 >> /var/log/ovs 2>&1

# Samba port
ovs-vsctl add-port ovsbr0 samba -- set interface samba type=geneve options:remote_ip=172.31.255.100 >> /var/log/ovs 2>&1

# Handle trunk interface mapping (similar to hypervisor)
if [ -z ${HYPERVISOR_HOST_TRUNK_INTERFACE+x} ];
then
    echo "$(date): INFO: No VPN trunk interface set in isardvdi.cfg"
else
    echo "$(date): INFO: Activating RSTP for VPN trunk"
    ovs-vsctl set Bridge ovsbr0 rstp_enable=true
    echo "$(date): INFO: Setting VPN trunk interface: '$HYPERVISOR_HOST_TRUNK_INTERFACE'"
    ovs-vsctl add-port ovsbr0 $HYPERVISOR_HOST_TRUNK_INTERFACE
    echo "$(date): INFO: VPN trunk interface $HYPERVISOR_HOST_TRUNK_INTERFACE added to OVS bridge"
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
dhcp-range=10.2.0.21,10.2.255.254,255.255.0.0
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

echo "$(date): INFO: Starting dnsmasq wireguard server"
/usr/sbin/dnsmasq --conf-file=/etc/dnsmasq.d/vlan-wg.conf --dhcp-script=/dnsmasq-hook/update-client-ips.sh >> /var/log/dnsmasq 2>&1 &
