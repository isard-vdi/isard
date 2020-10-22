package hyper

import (
	"libvirt.org/libvirt-go"
)

// Get returns a running desktop using it's name
func (h *Hyper) Get(name string) (*libvirt.Domain, error) {
	return h.conn.LookupDomainByName(name)
}
