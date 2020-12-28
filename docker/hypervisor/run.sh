rm -rf /run/libvirt/*
echo "Generating selfsigned certs for spice client..."
sh auto-generate-certs.sh
echo "Starting libvirt daemon..."
chown root:kvm /dev/kvm
/usr/sbin/virtlogd &
sleep 2
/usr/sbin/libvirtd &
sleep 1
#/usr/bin/virsh net-start default
sh -c "/vlans-discover.sh"

# Allows hyper to reach wireguard clients
ip r a 10.200.200.0/24 via 192.168.119.2

FILES=/etc/libvirt/qemu/networks/*
for f in $FILES
do
  filename=$(basename -- "$f")
  filename="${filename%.*}"
  if [ $filename != "autostart" ]; then
    echo "Activating network: $filename"
    /usr/bin/virsh net-start $filename
    /usr/bin/virsh net-autostart $filename
  fi
done


echo "Checking hypervisor..."
echo "[1/1] basic domain start..."
virsh create checks/domain.xml
virsh destroy domain
ssh-keygen -A -f /usr/local/
/usr/sbin/sshd -D -e -f /etc/ssh/sshd_config
