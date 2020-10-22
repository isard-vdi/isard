package hyper

import (
	"libvirt.org/libvirt-go"
)

// XMLGet returns the running XML definition of a desktop
func (h *Hyper) XMLGet(desktop *libvirt.Domain) (string, error) {
	xml, err := desktop.GetXMLDesc(libvirt.DOMAIN_XML_SECURE)
	if err != nil {
		return "", err
	}

	return xml, nil
}
