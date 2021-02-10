package model

import (
	"context"
	"time"

	"github.com/go-pg/pg/v10"
)

type Entity struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	AuthConfigs []*AuthConfig `pg:"rel:has-many"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

var _ pg.BeforeInsertHook = (*Entity)(nil)

func (e *Entity) BeforeInsert(ctx context.Context) (context.Context, error) {
	e.CreatedAt = time.Now()
	e.UpdatedAt = time.Now()

	return ctx, nil
}
