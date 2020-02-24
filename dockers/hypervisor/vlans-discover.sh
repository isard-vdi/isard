eth=$(ip link | awk -F: '$0 ~ "eth1"{print $2;getline}')
if [ -z $eth ]; then
	echo "Trunk interface not found."
else
	echo "Wait, scanning trunk interface for VLANS for 1 minute..."
	tshark -a duration:60 -i eth1 -Y "vlan" -x -V 2>&1 |grep -o " = ID: .*" |awk '{ print $NF }'  > out
	cat out | sort -u > vlans
	rm out
	VLANS=$(cat vlans |tr "\n" " ")
	for VLAN in $VLANS
	do
	        echo "FOUND VLAN: $VLAN"
	        echo "Creating vlan interface v$VLAN..."
	        ip link add name v$VLAN link eth1 type vlan id $VLAN
        	ip link set v$VLAN up
	        echo "   Created vlan interface: v$VLAN."
	done
	echo "You can now configure those Internet vlan interfaces in Isard hypervisor."
fi
