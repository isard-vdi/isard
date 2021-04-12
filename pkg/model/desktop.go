package model

import (
	"context"
	"fmt"
	"time"

	"github.com/go-pg/pg/v10"
)

// Desktop is a desktop represented in the DB
type Desktop struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	HardwareID  int       `pg:",notnull"`
	Hardware    *Hardware `pg:"rel:has-one"`
	UserID      int       `pg:",notnull"`
	User        *User     `pg:"rel:has-one"`
	EntityID    int       `pg:",notnull"`
	Entity      *Entity   `pg:"rel:has-one"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

// LoadWithUUID loads a desktop using its UUID
func (u *Desktop) LoadWithUUID(ctx context.Context, db *pg.DB) error {
	if err := db.Model(u).
		Relation("Hardware").
		Relation("Hardware.Base").
		Relation("Hardware.Disks").
		Relation("Hardware.Disks.Disk").
		Relation("Entity.uuid").
		Relation("User.uuid").
		Where("desktop.uuid = ?", u.UUID).
		Limit(1).Select(); err != nil {
		return fmt.Errorf("load desktop from db: %w", err)
	}

	return nil
}
