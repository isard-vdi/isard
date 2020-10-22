package hyper

import (
	"fmt"

	"libvirt.org/libvirt-go"
)

// Migrate migrates a running desktop to another hypervisor using PEER2PEER method
func (h *Hyper) Migrate(d *libvirt.Domain, hyperURI string) error {
	name, err := d.GetName()
	if err != nil {
		return fmt.Errorf("get desktop name: %w", err)
	}

	if err := d.MigrateToURI(hyperURI, libvirt.MIGRATE_PEER2PEER, name, 0); err != nil {
		return err
	}

	return nil
}
