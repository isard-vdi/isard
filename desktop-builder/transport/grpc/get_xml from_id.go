package grpc

import (
	"context"
	"fmt"

	"github.com/isard-vdi/isard/desktop-builder/pkg/proto"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (h *DesktopBuilderServer) GetXmlFromId(ctx context.Context, req *proto.GetXmlFromIdRequest) (*proto.GetXmlFromIdResponse, error) {
	return &proto.GetXmlFromIdResponse{Xml: XmlId(req.Xml, req.Id)}, nil
	return nil, status.Error(codes.Unimplemented, "not implemented yet")
}

func XmlId(xml string, id string) string {
	if xml == "win10" {
		return fmt.Sprintf(`<domain type='kvm'>
		<name>%s</name>
		<memory unit='KiB'>4294656</memory>
		<currentMemory>2097152</currentMemory>
		<vcpu placement='static'>4</vcpu>
		<os>
		  <type arch='x86_64'>hvm</type>
		  <boot dev='hd'/>
		  <bootmenu enable='no'/>
		</os>
		<features>
		  <acpi/>
		  <apic/>
		  <vmport state='off'/>
		  <hyperv>
			<relaxed state='on'/>
			<vapic state='on'/>
			<spinlocks state='on' retries='8191'/>
		  </hyperv>
		</features>
		<cpu mode='custom' match='exact'>
		  <model>Haswell-noTSX</model>
		</cpu>
		<clock offset='localtime'>
		  <timer name='rtc' tickpolicy='catchup'/>
		  <timer name='pit' tickpolicy='delay'/>
		  <timer name='hpet' present='no'/>
		  <timer name='hypervclock' present='yes'/>
		</clock>
		<pm>
		  <suspend-to-mem enabled='no'/>
		  <suspend-to-disk enabled='no'/>
		</pm>
		<devices>
		  <emulator>/usr/bin/qemu-kvm</emulator>
		  <disk type='file' device='disk'>
			<driver name='qemu' type='qcow2'/>
			<source file='/isard/groups/admin/admin/admin/%s.qcow2'/>
			<target dev='vda' bus='virtio'/>
		  </disk>
		  <controller type='usb' index='0' model='ich9-ehci1'/>
		  <controller type='usb' index='0' model='ich9-uhci1'>
			<master startport='0'/>
		  </controller>
		  <controller type='usb' index='0' model='ich9-uhci2'>
			<master startport='2'/>
		  </controller>
		  <controller type='usb' index='0' model='ich9-uhci3'>
			<master startport='4'/>
		  </controller>
		  <interface type='network'>
			<source network='default'/>
			<model type='virtio'/>
		  </interface>
		  <input type='tablet' bus='usb'/>
		  <graphics type='spice' port='-1' tlsPort='-1' autoport='yes'>
			<image compression='off'/>
		  </graphics>
		  <console type='pty'/>
		  <channel type='spicevmc'>
			<target type='virtio' name='com.redhat.spice.0'/>
		  </channel>
		  <sound model='ich6'/>
		  <video>
			<model type='qxl'/>
		  </video>
		  <redirdev bus='usb' type='spicevmc'/>
		  <redirdev bus='usb' type='spicevmc'/>
		</devices>
		</domain>`, id, id)
	}
	if xml == "linkat" {
		return fmt.Sprintf(`<domain type="kvm">
		<name>%s</name>
		<memory unit="KiB">2683904</memory>
		<currentMemory>2097152</currentMemory>
		<vcpu placement="static">2</vcpu>
		<os>
		  <type arch="x86_64">hvm</type>
		  <boot dev="hd"/>
		  <bootmenu enable="no"/>
		</os>
		<features>
		  <acpi/>
		  <apic/>
		  <vmport state="off"/>
		</features>
		<cpu mode="custom" match="exact">
		  <model>Haswell-noTSX</model>
		</cpu>
		<clock offset="utc">
		  <timer name="rtc" tickpolicy="catchup"/>
		  <timer name="pit" tickpolicy="delay"/>
		  <timer name="hpet" present="no"/>
		</clock>
		<pm>
		  <suspend-to-mem enabled="no"/>
		  <suspend-to-disk enabled="no"/>
		</pm>
		<devices>
		  <emulator>/usr/bin/qemu-kvm</emulator>
		  <disk type="file" device="disk">
			<driver name="qemu" type="qcow2"/>
			<source file="/isard/groups/admin/admin/admin/%s.qcow2"/>
			<target dev="vda" bus="virtio"/>
		  </disk>
		  <controller type="usb" index="0" model="ich9-ehci1"/>
		  <controller type="usb" index="0" model="ich9-uhci1">
			<master startport="0"/>
		  </controller>
		  <controller type="usb" index="0" model="ich9-uhci2">
			<master startport="2"/>
		  </controller>
		  <controller type="usb" index="0" model="ich9-uhci3">
			<master startport="4"/>
		  </controller>
		  <interface type="network">
			<source network="default"/>
			<model type="virtio"/>
		  </interface>
		  <input type="tablet" bus="usb"/>
		  <graphics type="spice" port="-1" tlsPort="-1" autoport="yes">
			<image compression="off"/>
		  </graphics>
		  <console type="pty"/>
		  <channel type="spicevmc">
			<target type="virtio" name="com.redhat.spice.0"/>
		  </channel>
		  <sound model="ich6"/>
		  <video>
			<model type="qxl"/>
		  </video>
		  <redirdev bus="usb" type="spicevmc"/>
		  <redirdev bus="usb" type="spicevmc"/>
		</devices>
	  </domain>`, id, id)
	}
	if xml == "win8.1" {
		return fmt.Sprintf(`<domain type="kvm">
		<name>%s</name>
		<memory unit="KiB">4294656</memory>
		<currentMemory>2097152</currentMemory>
		<vcpu placement="static">4</vcpu>
		<os firmware="efi">
		  <type arch="x86_64">hvm</type>
		  <loader readonly="yes" type="pflash">/usr/share/OVMF/OVMF.fd</loader>
		  <boot dev="hd"/>
		  <bootmenu enable="no"/>
		</os>
		<features>
		  <acpi/>
		  <apic/>
		  <vmport state="off"/>
		  <hyperv>
			<relaxed state="on"/>
			<vapic state="on"/>
			<spinlocks state="on" retries="8191"/>
		  </hyperv>
		</features>
		<cpu mode="custom" match="exact">
		  <model>Haswell-noTSX</model>
		</cpu>
		<clock offset="localtime">
		  <timer name="rtc" tickpolicy="catchup"/>
		  <timer name="pit" tickpolicy="delay"/>
		  <timer name="hpet" present="no"/>
		  <timer name="hypervclock" present="yes"/>
		</clock>
		<pm>
		  <suspend-to-mem enabled="no"/>
		  <suspend-to-disk enabled="no"/>
		</pm>
		<devices>
		  <emulator>/usr/bin/qemu-kvm</emulator>
		  <disk type="file" device="disk">
			<driver name="qemu" type="qcow2"/>
			<source file="/isard/templates/admin/admin/admin/%s.qcow2"/>
			<target dev="sda" bus="sata"/>
		  </disk>
		  <controller type="usb" index="0" model="ich9-ehci1"/>
		  <controller type="usb" index="0" model="ich9-uhci1">
			<master startport="0"/>
		  </controller>
		  <controller type="usb" index="0" model="ich9-uhci2">
			<master startport="2"/>
		  </controller>
		  <controller type="usb" index="0" model="ich9-uhci3">
			<master startport="4"/>
		  </controller>
		  <interface type="network">
			<source network="default"/>
			<model type="virtio"/>
		  </interface>
		  <input type="tablet" bus="usb"/>
		  <graphics type="spice" port="-1" tlsPort="-1" autoport="yes">
			<image compression="off"/>
		  </graphics>
		  <console type="pty"/>
		  <channel type="spicevmc">
			<target type="virtio" name="com.redhat.spice.0"/>
		  </channel>
		  <sound model="ich6"/>
		  <video>
			<model type="qxl"/>
		  </video>
		  <redirdev bus="usb" type="spicevmc"/>
		  <redirdev bus="usb" type="spicevmc"/>
		</devices>
	  </domain>`, id, id)
	}
	return ""
}
