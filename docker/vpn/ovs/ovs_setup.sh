ovsdb-server --detach --remote=punix:/var/run/openvswitch/db.sock --pidfile=ovsdb-server.pid --remote=ptcp:6640
ovs-vswitchd --detach --verbose --pidfile
ovs-vsctl add-br ovsbr0
ip link set ovsbr0 up

ovs-vsctl add-port ovsbr0 vlan-wg tag=4095 -- set interface vlan-wg type=internal
ip a a 10.2.0.1/16 dev vlan-wg
ip link set vlan-wg up

mkdir /var/run/dnsmasq
mkdir /var/lib/dnsmasq
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
dhcp-lease-max=490
dhcp-hostsfile=/var/lib/ovs-vlan-wg.hostsfile
dhcp-option=121,10.0.0.0/14,10.2.0.1
#dhcp-option=vlan-wg,3,10.2.0.1
dhcp-script=/dnsmasq-hook/update-client-ips.sh
dhcp-leasefile=/var/lib/misc/vlan-wg.leases
dhcp-option=3
EOT




# echo "dhcp-range=192.168.55.50,192.168.55.150,12h" > /etc/dnsmasq.d/vlan-wg.conf
# echo "dhcp-script=/update-client-ips.sh"
env > /tmp/env # This is needed by the dnsmasq-hook to get the envvars
/usr/sbin/dnsmasq --conf-file=/etc/dnsmasq.d/vlan-wg.conf --leasefile-ro --dhcp-script=/dnsmasq-hook/update-client-ips.sh &

ovs-vsctl show

# ip a f eth0
# #ovs-vsctl add-port ovsbr0 eth0
# ovs-vsctl add-port ovsbr0 eth0 tag=1 vlan_mode=native-tagged

# ip a a 172.18.255.17/24 dev ovsbr0
# ip r a default via 172.18.255.1 dev ovsbr0

# ovs-vsctl set bridge ovsbr0 protocols=OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13
# # ovs-vsctl set-controller ovsbr0 tcp:172.18.255.99:6653

# ovs-vsctl add-port ovsbr0 vxlan0 -- set interface vxlan0 type=vxlan options:remote_ip=<REMOTE_IP>



## ADD INTERNAL VLAN PORT


## SETUP DNSMASQ
#(apk add dnsmasq)
#echo "dhcp-range=192.168.55.50,192.168.55.150,12h" > /etc/dnsmasq.d/vlan-wg.conf
