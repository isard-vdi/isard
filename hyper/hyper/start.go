package hyper

import (
	"errors"
	"fmt"

	"libvirt.org/libvirt-go"
)

// Start starts a new machine using the provided XML
func (h *Hyper) Start(xml string, paused bool) (string, error) {
	flag := libvirt.DOMAIN_NONE
	if paused {
		flag = libvirt.DOMAIN_START_PAUSED
	}

	desktop, err := h.conn.DomainCreateXML(xml, flag)
	if err != nil {
		var e libvirt.Error
		if errors.As(err, &e) {
			switch e.Code {
			case libvirt.ERR_XML_ERROR:
				return "", fmt.Errorf("create desktop: %w", e)

			default:
				return "", fmt.Errorf("create desktop: %s", e.Message)
			}
		}

		return "", fmt.Errorf("create desktop: %w", err)
	}
	defer desktop.Free()

	xml, err = desktop.GetXMLDesc(libvirt.DOMAIN_XML_SECURE)
	if err != nil {
		return "", fmt.Errorf("get desktop XML: %w", err)
	}

	return xml, nil
}
