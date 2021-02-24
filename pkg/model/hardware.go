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

	VCPUs     int     `pg:",notnull"`
	MemoryMin int     `pg:",notnull"`
	MemoryMax int     `pg:",notnull"`
	Disks     []*Disk `pg:"rel:has-many"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

var _ pg.BeforeInsertHook = (*Hardware)(nil)

func (h *Hardware) BeforeInsert(ctx context.Context) (context.Context, error) {
	h.CreatedAt = time.Now()
	h.UpdatedAt = time.Now()

	return ctx, nil
}

type HardwareBase struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	OS          string `pg:",notnull"`
	OSVariant   string
	XML         string `pg:",notnull"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

var _ pg.BeforeInsertHook = (*HardwareBase)(nil)

func (h *HardwareBase) BeforeInsert(ctx context.Context) (context.Context, error) {
	h.CreatedAt = time.Now()
	h.UpdatedAt = time.Now()

	return ctx, nil
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

	MAC   string `pg:",notnull"`
	Order int

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
