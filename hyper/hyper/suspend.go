package hyper

import (
	"libvirt.org/libvirt-go"
)

// Suspend suspends a running desktop temporarily saving its memory state. It won't persist if the hypervisor restarts
func (h *Hyper) Suspend(desktop *libvirt.Domain) error {
	return desktop.Suspend()
}
