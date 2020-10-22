package desktopbuilder

import (
	"fmt"
	"strings"

	"gitlab.com/isard/isardvdi/common/pkg/model"
	libvirtxml "libvirt.org/libvirt-go-xml"
)

func BuildDesktop(desktop *model.Desktop) (string, error) {
	os, err := buildOS(desktop)
	if err != nil {
		return "", err
	}

	dom := &libvirtxml.Domain{
		Name: desktop.ID,
		OS:   os,
		VCPU: &libvirtxml.DomainVCPU{
			Value: desktop.VCPUs,
		},
		Memory: &libvirtxml.DomainMemory{
			Value: desktop.RAM,
			Unit:  "MiB",
		},
		CPU: &libvirtxml.DomainCPU{
			Mode: "",
		},
	}

	return dom.Marshal()
}

func buildOS(desktop *model.Desktop) (*libvirtxml.DomainOS, error) {
	os := &libvirtxml.DomainOS{}

	switch desktop.Type {
	case model.DesktopTypeEnumBIOS:
		buildOSBIOS(desktop.TypeBIOS, os)

	default:
		return nil, fmt.Errorf("unknown OS type: '%s'", desktop.Type.String())
	}

	return os, nil
}

func buildOSBIOS(d *model.DesktopTypeBIOS, os *libvirtxml.DomainOS) {
	if d == nil {
		d = &model.DesktopTypeBIOS{}
	}

	if d.FirmwareType != model.DesktopFirmwareTypeUnknown {
		os.Firmware = strings.ToLower(d.FirmwareType.String())
	}

	os.Type = &libvirtxml.DomainOSType{}

	if d.OSType != model.DesktopOSTypeUnknown {
		os.Type.Type = strings.ToLower(d.OSType.String())
	} else {
		os.Type.Type = "hvm"
	}

	os.Type.Arch = d.Arch

	if d.Machine != "" {
		os.Type.Machine = d.Machine
	} else {
		os.Type.Machine = "q35"
	}

	os.BootDevices = []libvirtxml.DomainBootDevice{}
	for _, b := range d.Boot {
		os.BootDevices = append(os.BootDevices, libvirtxml.DomainBootDevice{
			Dev: strings.ToLower(b.String()),
		})
	}
}
