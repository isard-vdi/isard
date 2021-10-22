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
dhcp-hostsfile=/var/lib/ovs-vlan-wg.hostsfile
dhcp-option=121,10.0.0.0/14,10.2.0.1
dhcp-option=26,1366
#dhcp-option=vlan-wg,3,10.2.0.1
dhcp-script=/dnsmasq-hook/update-client-ips.sh
dhcp-leasefile=/var/lib/misc/vlan-wg.leases
dhcp-option=3
dhcp-ignore-names
dhcp-ignore-clid
EOT




# echo "dhcp-range=192.168.55.50,192.168.55.150,12h" > /etc/dnsmasq.d/vlan-wg.conf
# echo "dhcp-script=/update-client-ips.sh"
echo "$(date): INFO: Starting dnsmasq wireguard server"
/usr/sbin/dnsmasq --conf-file=/etc/dnsmasq.d/vlan-wg.conf --dhcp-script=/dnsmasq-hook/update-client-ips.sh >> /var/log/dnsmasq 2>&1 &

# ip a f eth0
# #ovs-vsctl add-port ovsbr0 eth0
# ovs-vsctl add-port ovsbr0 eth0 tag=1 vlan_mode=native-tagged

# ip a a 172.31.255.17/24 dev ovsbr0
# ip r a default via 172.31.255.1 dev ovsbr0

# ovs-vsctl set bridge ovsbr0 protocols=OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13
# # ovs-vsctl set-controller ovsbr0 tcp:172.31.255.99:6653

# ovs-vsctl add-port ovsbr0 vxlan0 -- set interface vxlan0 type=vxlan options:remote_ip=<REMOTE_IP>



## ADD INTERNAL VLAN PORT


## SETUP DNSMASQ
#(apk add dnsmasq)
#echo "dhcp-range=192.168.55.50,192.168.55.150,12h" > /etc/dnsmasq.d/vlan-wg.conf
