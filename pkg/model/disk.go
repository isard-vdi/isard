//go:generate stringer -type=DiskType -trimprefix=DiskType

package model

import (
	"context"
	"fmt"
	"time"

	"github.com/go-pg/pg/v10"
)

// Disk is a disk represented in the DB
type Disk struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Type     DiskType `pg:",notnull"`
	ParentID int
	Parent   *Disk   `pg:"rel:has-one"`
	EntityID int     `pg:",notnull"`
	Entity   *Entity `pg:"rel:has-one"`
	UserID   int     `pg:",notnull"`
	User     *User   `pg:"rel:has-one"`
	// TODO: Size?

	Name        string `pg:",notnull"`
	Description string

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type DiskType int

const (
	DiskTypeUnknown DiskType = iota
	DiskTypeQcow2
	DiskTypeRaw
	DiskTypeISO
	DiskTypeFloppy
	DiskTypeUSB
)

func (d *Disk) LoadWithUUID(ctx context.Context, db *pg.DB) error {
	if err := loadWithUUID(ctx, db, d, d.UUID); err != nil {
		return fmt.Errorf("load disk from the db: %w", err)
	}

	return nil
}
