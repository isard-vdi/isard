package diskoperations

import (
	"errors"
	"fmt"
	"os/exec"
	"path"

	"github.com/spf13/afero"
)

var (
	ErrBackingFileNotFound = errors.New("backing file not found")
)

func (d *DiskOperations) Derivate(name, backingFile string, clusterSize int) error {
	if _, err := d.env.FS.Stat(backingFile); errors.Is(err, afero.ErrFileNotFound) {
		return ErrBackingFileNotFound
	}

	dir := path.Dir(name)
	if _, err := d.env.FS.Stat(dir); errors.Is(err, afero.ErrFileNotFound) {
		if err := d.env.FS.MkdirAll(dir, 0755); err != nil {
			return fmt.Errorf("create disk directory: %w", err)
		}
	}

	cmd := exec.Command("qemu-img", "create", "-f", "qcow2", "-o", fmt.Sprintf("cluster_size=%d", clusterSize), "-b", backingFile, name)
	if out, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("create derivation: %w: %s", err, out)
	}

	return nil
}
