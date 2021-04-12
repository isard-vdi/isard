package diskoperations

import (
	"errors"
	"fmt"
	"os/exec"
	"path/filepath"
	"strconv"

	"github.com/rs/xid"
	"github.com/spf13/afero"
	"gitlab.com/isard/isardvdi/pkg/model"
	"gitlab.com/isard/isardvdi/pkg/storage"
)

func (d *DiskOperations) Create(t model.DiskType, size, uID, eID int, name, description string) (int, error) {
	u := &model.User{ID: uID}
	if err := d.db.Model(u).Column("uuid").Select(); err != nil {
		return 0, fmt.Errorf("get user uuid: %w", err)
	}

	e := &model.Entity{ID: eID}
	if err := d.db.Model(e).Column("uuid").Select(); err != nil {
		return 0, fmt.Errorf("get entity uuid: %w", err)
	}

	disk := &model.Disk{
		UUID: xid.New().String(),
		Type: t,

		EntityID: eID,
		UserID:   uID,

		Name:        name,
		Description: description,
	}

	diskPath := storage.DiskPath(d.basePath, e.UUID, u.UUID, disk.UUID)
	diskDir := filepath.Dir(diskPath)

	exists, err := afero.DirExists(d.fs, diskDir)
	if err != nil {
		return 0, fmt.Errorf("check disk directory exists: %w", err)
	}

	if !exists {
		if err := d.fs.MkdirAll(diskDir, 0755); err != nil {
			return 0, fmt.Errorf("create disk directory: %w", err)
		}
	}

	switch t {
	case model.DiskTypeQcow2:
		diskPath += ".qcow2"

		if err := createQCow2(diskPath, size); err != nil {
			return 0, fmt.Errorf("create qcow2 disk: %w", err)
		}

	default:
		return 0, errors.New("disk type not implemented yet")
	}

	if _, err := d.db.Model(disk).Returning("id").Insert(); err != nil {
		d.fs.Remove(diskPath)

		return 0, fmt.Errorf("add disk to db: %w", err)
	}

	return disk.ID, nil
}

func createQCow2(path string, size int) error {
	b, err := exec.Command("qemu-img", "create",
		"-f", "qcow2",
		// TODO: Check performance and disk space
		"-o", "cluster_size=4k",
		// "-o", "preallocation=metadata",
		path, strconv.Itoa(size)+"M").CombinedOutput()
	if err != nil {
		return fmt.Errorf("qemu-img error: %s", b)
	}

	return nil
}
