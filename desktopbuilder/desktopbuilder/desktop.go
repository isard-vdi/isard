package desktopbuilder

import (
	"gitlab.com/isard/isardvdi/pkg/model"

	libvirtxml "libvirt.org/libvirt-go-xml"
)

func BuildDesktop(desktop *model.Desktop) (string, error) {
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
	// TODO: Disks & interfaces, OS variant
	return dom.Marshal()
}
