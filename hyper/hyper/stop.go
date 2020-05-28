package hyper

import (
	"errors"
	"fmt"

	"libvirt.org/libvirt-go"
)

var (
	ErrDesktopNotStarted = errors.New("desktop is not started")
)

func (h *Hyper) Stop(id string) error {
	desktop, err := h.conn.LookupDomainByName(id)
	if err != nil {
		var e libvirt.Error
		if errors.As(err, &e) {
			switch e.Code {
			case libvirt.ERR_NO_DOMAIN:
				return ErrDesktopNotStarted

			default:
				return fmt.Errorf("stop desktop: %s", e.Message)
			}
		}

		return fmt.Errorf("stop desktop: %w", err)
	}
	defer desktop.Free()

	return nil
}
