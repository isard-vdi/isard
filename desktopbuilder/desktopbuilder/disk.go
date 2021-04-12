package desktopbuilder

import (
	"gitlab.com/isard/isardvdi/pkg/model"
	"gitlab.com/isard/isardvdi/pkg/storage"
	libvirtxml "libvirt.org/libvirt-go-xml"
)

// abc is used to generate the disk device
const abc = "abcdefghijklmnopqrstuvwxyz"

// buildDisk generates the libvirt XML for a specific disk
func (d *DesktopBuilder) buildDisk(desktop *model.Desktop, disk *model.HardwareDisk, order int) libvirtxml.DomainDisk {
	domDisk := libvirtxml.DomainDisk{}

	switch disk.Disk.Type {
	case model.DiskTypeQcow2:
		domDisk.Device = "disk"
		domDisk.Driver = &libvirtxml.DomainDiskDriver{
			Name: "qemu",
			Type: "qcow2",
		}
		domDisk.Source = &libvirtxml.DomainDiskSource{
			File: &libvirtxml.DomainDiskSourceFile{
				File: storage.DiskPath(d.storageBasePath, desktop.Entity.UUID, desktop.User.UUID, disk.Disk.UUID) + ".qcow2",
			},
		}
		domDisk.Target = &libvirtxml.DomainDiskTarget{
			// Choose the letter from the abecedarium, using the disk order
			Dev: "sd" + abc[order:order+1],
			// TODO: Check bus
			Bus: "virtio",
		}

	case model.DiskTypeUSB:
		// Removable: ON!
	}

	return domDisk
}

// diskOrder is used to sort the disks using the Order value
type diskOrder []*model.HardwareDisk

// Len returns the lenght of the list
func (d diskOrder) Len() int {
	return len(d)
}

// Swap changes the position between two items
func (d diskOrder) Swap(i, j int) {
	d[i], d[j] = d[j], d[i]
}

// Less is used to check which item should be first
func (d diskOrder) Less(i, j int) bool {
	return d[i].Order < d[j].Order
}
