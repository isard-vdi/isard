package desktopbuilder

import (
	"context"
	"fmt"
	"sort"

	"gitlab.com/isard/isardvdi/pkg/model"

	libvirtxml "libvirt.org/libvirt-go-xml"
)

// XMLGet creates the XML for a desktop
func (d *DesktopBuilder) XMLGet(ctx context.Context, id string) (string, error) {
	desktop := &model.Desktop{UUID: id}
	if err := desktop.LoadWithUUID(ctx, d.db); err != nil {
		return "", fmt.Errorf("load the desktop from the db: %w", err)
	}

	dom := &libvirtxml.Domain{}
	if err := dom.Unmarshal(desktop.Hardware.Base.XML); err != nil {
		return "", err
	}

	dom.Name = desktop.UUID
	dom.Description = desktop.Name
	dom.VCPU = &libvirtxml.DomainVCPU{
		Value: uint(desktop.Hardware.VCPUs),
	}
	dom.Memory = &libvirtxml.DomainMemory{
		Unit: "MiB",
		// TODO: Max & min RAM
		Value: uint(desktop.Hardware.Memory),
	}

	sort.Sort(diskOrder(desktop.Hardware.Disks))
	for i, disk := range desktop.Hardware.Disks {
		dom.Devices.Disks = append(dom.Devices.Disks, d.buildDisk(desktop, disk, i))
	}

	// TODO: Network interfaces, OS type
	// TODO: Floppy disks and IDE are not supported in the Q35 CPU
	return dom.Marshal()
}
