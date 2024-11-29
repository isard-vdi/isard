#!/bin/sh -i

ovsdb-server --detach --remote=punix:/var/run/openvswitch/db.sock --pidfile=ovsdb-server.pid --remote=ptcp:6640 >/tmp/ovsdb-server.out 2>&1
ovs-vswitchd --detach --verbose --pidfile >/tmp/ovs-vswitchd.out 2>&1
ovs-vsctl add-br ovsbr0
ip link set ovsbr0 up

ovs-vsctl add-port ovsbr0 bastion -- set interface bastion type=geneve options:remote_ip=172.31.255.23
ovs-vsctl add-port ovsbr0 vlan-wg tag=4095 -- set interface vlan-wg type=internal >> /var/log/ovs 2>&1
ip a a 10.2.0.2/16 dev vlan-wg >> /var/log/ovs 2>&1
ip link set vlan-wg up >> /var/log/ovs 2>&1

ovs-vsctl show

/bastion