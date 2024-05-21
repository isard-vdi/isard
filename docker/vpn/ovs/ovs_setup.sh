echo "$(date): INFO: Starting OpenVSWitch server"
ovsdb-server --detach --remote=punix:/var/run/openvswitch/db.sock --pidfile=ovsdb-server.pid --remote=ptcp:6640  > /var/log/ovs 2>&1
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
