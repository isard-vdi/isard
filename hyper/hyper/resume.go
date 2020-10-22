package hyper

import (
	"libvirt.org/libvirt-go"
)

// Resume resumes a suspended desktop to its original running state, continuing the execution where it was left
func (h *Hyper) Resume(desktop *libvirt.Domain) error {
	return desktop.Resume()
}
