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

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
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
