package diskoperations

import (
	"github.com/go-pg/pg/v10"
	"github.com/spf13/afero"
	"gitlab.com/isard/isardvdi/pkg/model"
)

type Interface interface {
	// TODO: Check free space before creating the disk
	Create(t model.DiskType, size, uID, eID int, name, description string) (int, error)
}

type DiskOperations struct {
	db       *pg.DB
	fs       afero.Fs
	basePath string
}

func New(db *pg.DB, fs afero.Fs, basePath string) *DiskOperations {
	return &DiskOperations{db, fs, basePath}
}
