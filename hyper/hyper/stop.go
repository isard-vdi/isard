package hyper

import (
	"libvirt.org/libvirt-go"
)

// Stop stops a running desktop
func (h *Hyper) Stop(desktop *libvirt.Domain) error {
	return desktop.Destroy()
}
