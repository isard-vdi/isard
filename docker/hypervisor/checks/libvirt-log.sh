if [ $1 == "set" ]; then
    virt-admin daemon-log-filters "1:util 1:libvirt 1:storage 1:network 1:nodedev 1:qemu"
    virt-admin daemon-log-filters
    virt-admin daemon-log-outputs "1:file:/libvirt.log"
    virt-admin daemon-log-outputs
fi
if [ $1 == "unset" ]; then
    virt-admin daemon-log-filters ""
    virt-admin daemon-log-filters
    virt-admin daemon-log-outputs "3:stderr"
    virt-admin daemon-log-outputs
fi

