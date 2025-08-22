#!/bin/sh -i

# OVS Security Configuration - Always log for audit trail
echo "$(date '+%Y-%m-%d %H:%M:%S') [SECURITY] OVS Bastion setup starting"

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
ip link set ovsbr0 up

ovs-vsctl add-port ovsbr0 bastion -- set interface bastion type=geneve options:remote_ip=172.31.255.23
ovs-vsctl add-port ovsbr0 vlan-wg tag=4095 -- set interface vlan-wg type=internal >> /var/log/ovs 2>&1
ip a a 10.2.0.2/16 dev vlan-wg >> /var/log/ovs 2>&1
ip link set vlan-wg up >> /var/log/ovs 2>&1

ovs-vsctl show

/bastion