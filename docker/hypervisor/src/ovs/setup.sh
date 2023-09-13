ovsdb-server --detach --remote=punix:/var/run/openvswitch/db.sock --pidfile=ovsdb-server.pid --remote=ptcp:6640 >/tmp/ovsdb-server.out 2>&1
ovs-vswitchd --detach --verbose --pidfile >/tmp/ovs-vswitchd.out 2>&1
ovs-vsctl add-br ovsbr0
ip link set ovsbr0 up

ovs-vsctl add-port ovsbr0 $DOMAIN -- set interface $DOMAIN type=geneve options:remote_ip=10.1.0.1

if [ -z ${HYPERVISOR_HOST_TRUNK_INTERFACE+x} ];
then
    echo "No vlan interface set in isardvdi.cfg";
else
    echo "Activating RTSP"
    ovs-vsctl set Bridge ovsbr0 rstp_enable=true
    echo "Setting vlan interface: '$HYPERVISOR_HOST_TRUNK_INTERFACE'";
    ovs-vsctl add-port ovsbr0 $HYPERVISOR_HOST_TRUNK_INTERFACE
fi

ovs-vsctl show

# Every ARP request coming from isard-vpn should be flooded to all ports
ovs-ofctl add-flow ovsbr0 "priority=202,dl_type=0x0806,dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=10.2.0.1,actions=strip_vlan,output:all"

# ip a f eth0
#ovs-vsctl add-port ovsbr0 eth0
# ovs-vsctl add-port ovsbr0 eth0 tag=1 vlan_mode=native-tagged

# ip a a 172.31.255.17/24 dev ovsbr0
# ip r a default via 172.31.255.1 dev ovsbr0

# ovs-vsctl set bridge ovsbr0 protocols=OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13
# ovs-vsctl set-controller ovsbr0 tcp:172.31.255.99:6653

# ovs-vsctl add-port ovsbr0 vxlan0 -- set interface vxlan0 type=vxlan options:remote_ip=<REMOTE_IP>
