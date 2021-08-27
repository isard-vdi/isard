ovs-vsctl add-port ovsbr0 vx_main -- set interface vx_main type=vxlan options:remote_ip=$1 option:key=flow
