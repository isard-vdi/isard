package diskoperations

// import (
// 	"fmt"
// 	"path"

// 	"github.com/spf13/afero"
// 	"github.com/zchee/go-qcow2"
// )

// func (d *DiskOperations) Create(name string, size int64, format qcow2.DriverFmt, clusterSize int, prealloc qcow2.PreallocMode, lazyRefcounts bool) error {
// 	exists, err := afero.Exists(d.env.FS, name)
// 	if err != nil {
// 		return fmt.Errorf("check if disk exists: %w", err)
// 	}

// 	if exists {
// 		return nil
// 	}

// 	dir := path.Dir(name)
// 	exists, err = afero.DirExists(d.env.FS, dir)
// 	if err != nil {
// 		return fmt.Errorf("check if disk directory: %w", err)
// 	}

// 	if !exists {
// 		if err := d.env.FS.MkdirAll(dir, 0755); err != nil {
// 			return fmt.Errorf("create disk directory: %w", err)
// 		}
// 	}

// 	qcow2.Create(&qcow2.Opts{
// 		Filename:      name,
// 		Fmt:           format,
// 		Size:          size,
// 		Preallocation: prealloc,
// 	})

// 	return nil
// }
