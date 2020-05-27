package hyper

import (
	"errors"
	"fmt"

	"libvirt.org/libvirt-go"
)

func (h *Hyper) XMLGet(id string) (string, error) {
	desktop, err := h.conn.LookupDomainByName(id)
	if err != nil {
		var e libvirt.Error
		if errors.As(err, &e) {
			return "", fmt.Errorf("get desktop: %s", e.Message)
		}

		return "", fmt.Errorf("get desktop: %w", err)
	}
	defer desktop.Free()

	xml, err := desktop.GetXMLDesc(libvirt.DOMAIN_XML_SECURE)
	if err != nil {
		return "", fmt.Errorf("get desktop XML: %w", err)
	}

	return xml, nil
}
