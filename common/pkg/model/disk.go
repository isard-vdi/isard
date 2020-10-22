//go:generate stringer -type=DiskType -trimprefix=DiskType

package model

import "time"

type Disk struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	ParentID   int       `pg:",notnull"`
	Parent     *Disk     `pg:"rel:has-one"`
	HardwareID int       `pg:",notnull"`
	Hardware   *Hardware `pg:"rel:has-one"`

	Type     DiskType `pg:",notnull"`
	Path     string   `pg:",notnull"`
	Enable   bool
	ReadOnly bool
	Order    int
	Config   string

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type DiskType int

const (
	DiskTypeUnknown DiskType = iota
	DiskTypeQcow2
	DiskTypeRaw
)
