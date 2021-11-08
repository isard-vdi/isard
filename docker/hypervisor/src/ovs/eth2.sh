ovsdb-server --detach --remote=punix:/var/run/openvswitch/db.sock --pidfile=ovsdb-server.pid --remote=ptcp:6640
ovs-vswitchd --detach --verbose --pidfile
ovs-vsctl add-br ovsbr0
ip link set ovsbr0 up
ovs-vsctl show

ip a f eth2
ovs-vsctl add-port ovsbr0 eth2
#ovs-vsctl add-port ovsbr0 eth0 tag=1 vlan_mode=native-tagged

#ip a a 172.31.255.17/24 dev ovsbr0
#ip r a default via 172.31.255.1 dev ovsbr0

ovs-vsctl set bridge ovsbr0 protocols=OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13
ovs-vsctl set-controller ovsbr0 tcp:172.31.255.99:6653

ovs-vsctl add-port ovsbr0 vxlan0 -- set interface vxlan0 type=vxlan options:remote_ip=<REMOTE_IP>
