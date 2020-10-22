package hyper

import (
	"libvirt.org/libvirt-go"
)

// StartOptions are a set of parameters that modify how the desktop is started
type StartOptions struct {
	// Paused sets whether the desktop is paused when started or not
	Paused bool
}

// Start starts a new machine using the provided XML definition
// It's a non-persistent desktop from libvirt point of view
func (h *Hyper) Start(xml string, options *StartOptions) (*libvirt.Domain, error) {
	flag := libvirt.DOMAIN_NONE
	if options.Paused {
		flag = libvirt.DOMAIN_START_PAUSED
	}

	desktop, err := h.conn.DomainCreateXML(xml, flag)
	if err != nil {
		return nil, err
	}

	return desktop, nil
}
