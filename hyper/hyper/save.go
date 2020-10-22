package hyper

import (
	"libvirt.org/libvirt-go"
)

// Save saves a running desktop saving its memory state to a file. It will persist if the hypervisor restarts
func (h *Hyper) Save(desktop *libvirt.Domain, path string) error {
	return desktop.Save(path)
}
