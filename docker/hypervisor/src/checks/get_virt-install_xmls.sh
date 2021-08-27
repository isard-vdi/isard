apk add libosinfo virt-install py3-libvirt py3-libxml2 
osinfo-query os > osinfo.txt
touch /tmp/disk.qcow2 /tmp/cdrom.iso /tmp/floppy.img
mkdir xmls
for os in $(osinfo-query --fields=short-id os | tail -n +3); do \
virt-install --import --name $os  --os-variant $os --network=bridge=br \
--dry-run --print-xml --disk none --memory=2048 \
--disk /tmp/disk.qcow2,device=disk \
--disk /tmp/cdrom.iso,device=cdrom \
--disk /tmp/floppy.img,device=floppy \
--boot network,cdrom,fd,hd,menu=on\
> xmls/$os.xml; done