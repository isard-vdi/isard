echo "Generating selfsigned certs for spice client..."
sh auto-generate-certs.sh
echo "Starting libvirt daemon..."
chown root:kvm /dev/kvm
/usr/sbin/virtlogd &
/usr/sbin/libvirtd &
sleep 2
#/usr/bin/virsh net-start default
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
/usr/sbin/sshd -D -e -f /etc/ssh/sshd_config
