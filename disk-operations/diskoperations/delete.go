package diskoperations

import (
	"errors"
	"fmt"

	"github.com/spf13/afero"
)

func (d *DiskOperations) Delete(name string) error {
	if err := d.env.FS.Remove(name); err != nil {
		if !errors.Is(err, afero.ErrFileNotFound) {
			return fmt.Errorf("delete disk: %w", err)
		}
	}

	return nil
}
