package model

import (
	"context"
	"fmt"
	"time"

	"github.com/go-pg/pg/v10"
)

type Desktop struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	HardwareID  int       `pg:",notnull"`
	Hardware    *Hardware `pg:"rel:has-one"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

var _ pg.BeforeInsertHook = (*Desktop)(nil)

func (d *Desktop) BeforeInsert(ctx context.Context) (context.Context, error) {
	d.CreatedAt = time.Now()
	d.UpdatedAt = time.Now()

	return ctx, nil
}

func (u *Desktop) LoadWithUUID(ctx context.Context, db *pg.DB) error {
	if err := db.Model(u).
		Relation("Hardware").
		Relation("Hardware.Base").
		Where("desktop.uuid = ?", u.UUID).
		Limit(1).Select(); err != nil {
		return fmt.Errorf("load desktop from db: %w", err)
	}

	return nil
}
