package hyper

import (
	"errors"
	"fmt"

	"github.com/jinzhu/copier"
	"libvirt.org/libvirt-go"
)

func (h *Hyper) List() ([]libvirt.Domain, error) {
	d, err := h.conn.ListAllDomains(libvirt.CONNECT_LIST_DOMAINS_RUNNING)
	if err != nil {
		var e libvirt.Error
		if errors.As(err, &e) {
			return nil, fmt.Errorf("list desktops: %s", e.Message)
		}

		return nil, fmt.Errorf("list desktops: %w", err)
	}

	var desktops []libvirt.Domain
	for _, desktop := range d {
		defer desktop.Free()

		copiedDesktop := libvirt.Domain{}
		copier.Copy(&copiedDesktop, &desktop)

		desktops = append(desktops, copiedDesktop)
	}

	return desktops, nil
}
