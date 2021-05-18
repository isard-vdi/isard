#!/bin/sh

if [ -z "$HYPERVISOR_HOST_TRUNK_INTERFACE" ]; then
    echo "VLANS disabled."
	exit 0
elif [ ! -z "$HYPERVISOR_HOST_TRUNK_INTERFACE" ] & [ -z "$HYPERVISOR_STATIC_VLANS" ]; then
    echo "VLANS enabled for DYNAMIC discovery."
	eth=$HYPERVISOR_HOST_TRUNK_INTERFACE
	if [ -z $eth ]; then
		echo "Trunk interface not found. Not starting vlan autodiscovery."
		exit 0
	fi
	echo "Wait, scanning trunk interface for VLANS for 260 seconds..."
	tshark -a duration:260 -i $HYPERVISOR_HOST_TRUNK_INTERFACE -Y "vlan" -x -V 2>&1 |grep -o " = ID: .*" |awk '{ print $NF }'  > out
	cat out | sort -u > /root/.ssh/vlans
	rm out
elif [ ! -z "$HYPERVISOR_HOST_TRUNK_INTERFACE" ] & [ ! -z "$HYPERVISOR_STATIC_VLANS" ]; then
	echo "Configuring vlans $HYPERVISOR_STATIC_VLANS..."
	echo $HYPERVISOR_STATIC_VLANS | tr "," "\n" > /root/.ssh/vlans
else
	rm /root/.ssh/vlans
fi

VLANS=$(cat /root/.ssh/vlans |tr "\n" " ")
for VLAN in $VLANS
do
	echo "SETTING VLAN: $VLAN"
	echo "Creating vlan interface v$VLAN..."
	ip link add name v$VLAN link $HYPERVISOR_HOST_TRUNK_INTERFACE type vlan id $VLAN
	ip link set v$VLAN up
	echo "Creating bridge br-$VLAN"
	ip link add name br-$VLAN type bridge
	ip link set br-$VLAN up
	ip link set v$VLAN master br-$VLAN
	echo " + Created vlan interface: bridge br-$VLAN over vlan-if v$VLAN."
done
sh -c 'python3 vlans-db.py $(cat /root/.ssh/vlans |tr "\n" " ")'

if [ ${#VLANS[@]} > 0 ]; then
	echo "You can now configure those Internet bridge interfaces (vXXX) in Isard resources menu."
fi
