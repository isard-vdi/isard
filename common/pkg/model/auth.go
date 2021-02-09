package model

import (
	"context"
	"time"

	"github.com/go-pg/pg/v10"
)

type AuthConfig struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	EntityID    int     `pg:",notnull"`
	Entity      *Entity `pg:"rel:has-one"`
	Type        string  `pg:",notnull"`
	Config      string

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

var _ pg.BeforeInsertHook = (*AuthConfig)(nil)

func (a *AuthConfig) BeforeInsert(ctx context.Context) (context.Context, error) {
	a.CreatedAt = time.Now()
	a.UpdatedAt = time.Now()

	return ctx, nil
}
