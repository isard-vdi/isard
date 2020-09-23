if [[ -z $VLANS ]]
then
    echo "You should add environment variables:"
    echo "  docker exec -e VLANS=<vlan_id1,vlanid2,...> isard-hypervisor sh -c '/vlans-add.sh'"
    echo "Example VLANS"
    echo "  docker exec -e VLANS='10,11' isard-hypervisor sh -c '/vlans-add.sh'"
    echo "Please run it again setting environment variables"
    exit 1
fi

VLANS=$(echo $VLANS | tr "," " ")
for VLAN in $VLANS
do
       echo "Creating vlan interface v$VLAN..."
       ip link add name v$VLAN link eth1 type vlan id $VLAN
       ip link set v$VLAN up
       echo "Creating bridge br-$VLAN"
       ip link add name br-$VLAN type bridge
       ip link set br-$VLAN up
       ip link set v$VLAN master br-$VLAN
       echo " + Created vlan interface: bridge br-$VLAN over vlan-if v$VLAN."
       echo $VLAN >> /root/.ssh/vlans
done
echo "You can now configure those Internet vlan interfaces in Isard hypervisor."

