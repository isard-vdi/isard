V="10,11"
VLANS=$(echo $V | tr "," " ")
for VLAN in $VLANS
do
        echo "Creating vlan interface v$VLAN..."
        ip link add name v$VLAN link eth0 type vlan id $VLAN
        ip link set v$VLAN up
        echo "   Created vlan interface: v$VLAN."
done
echo "You can now configure those Internet vlan interfaces in Isard hypervisor."

