#!/bin/sh
mkdir -p /storage/virt-install/xmls
osinfo-query os > /storage/virt-install/osinfo.txt
libvirtd -p /tmp/libvirt.pid -d
for os in $(osinfo-query --fields=short-id os | tail -n +3); do echo $os && virt-install --import --name $os  --os-variant $os --network=bridge=br --dry-run --print-xml --disk none --memory=2048 > /storage/virt-install/xmls/$os.xml; done
kill -9 $(pidof libvirtd)
