package model

import (
	"context"
	"fmt"
	"time"

	"github.com/go-pg/pg/v10"
)

type Hardware struct {
	ID int

	BaseID     int                  `pg:",notnull"`
	Base       *HardwareBase        `pg:"rel:has-one"`
	Interfaces []*HardwareInterface `pg:"rel:has-many"`

	VCPUs     int     `pg:"vcpus,notnull"`
	MemoryMin int     `pg:",notnull"`
	MemoryMax int     `pg:",notnull"`
	Disks     []*Disk `pg:"rel:has-many"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type HardwareBase struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	OS          string `pg:",notnull"`
	OSVariant   string
	XML         string `pg:",notnull"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

func (h *HardwareBase) LoadWithUUID(ctx context.Context, db *pg.DB) error {
	if err := db.Model(h).
		Where("uuid = ?", h.UUID).
		Limit(1).Select(); err != nil {
		return fmt.Errorf("load hardware base from db: %w", err)
	}

	return nil
}

type HardwareInterface struct {
	InterfaceID int        `pg:",pk,notnull"`
	Interface   *Interface `pg:"rel:has-one"`
	HardwareID  int        `pg:",pk,notnull"`
	Hardware    *Hardware  `pg:"rel:has-one"`

	MAC   string `pg:",notnull"`
	Order int

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
