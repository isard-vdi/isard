package model

import (
	"context"
	"fmt"
	"time"

	"github.com/go-pg/pg/v10"
)

type User struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	EntityID int     `pg:",notnull"`
	Entity   *Entity `pg:"rel:has-one"`
	GroupID  int     `pg:",notnull"`
	Group    *Group  `pg:"rel:has-one"`

	AuthConfigID int         `pg:",notnull"`
	AuthConfig   *AuthConfig `pg:"rel:has-one"`
	// Local login
	Username string
	Password string

	Name    string `pg:",notnull"`
	Surname string
	Email   string

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

func (u *User) Load(ctx context.Context, db *pg.DB) error {
	if err := db.Model(u).
		WherePK().
		Limit(1).Select(); err != nil {
		return fmt.Errorf("load user from db: %w", err)
	}

	return nil
}

func (u *User) LoadWithUUID(ctx context.Context, db *pg.DB) error {
	if err := db.Model(u).
		Where("uuid = ?", u.UUID).
		Limit(1).Select(); err != nil {
		return fmt.Errorf("load user from db: %w", err)
	}

	return nil
}

func (u *User) LoadWithUsername(ctx context.Context, db *pg.DB, entityUUID string) error {
	if err := db.Model(u).
		Relation("Entity").
		Where("entity.uuid = ?", entityUUID).
		Where("username = ?", u.Username).
		Limit(1).Select(); err != nil {
		return fmt.Errorf("load user from db: %w", err)
	}

	return nil
}
