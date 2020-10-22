package hyper

import (
	"libvirt.org/libvirt-go"
)

// List returns a list of all the running desktops
func (h *Hyper) List() ([]libvirt.Domain, error) {
	desktops, err := h.conn.ListAllDomains(libvirt.CONNECT_LIST_DOMAINS_RUNNING)
	if err != nil {
		return nil, err
	}

	return desktops, nil
}
