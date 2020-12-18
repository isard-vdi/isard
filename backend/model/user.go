package model

import (
	"context"
	"errors"
	"fmt"

	"github.com/go-pg/pg/v10"
)

const userIDFieldSeparator = "-"

type User struct {
	ID           string
	Provider     string
	Organization string

	// Username is used by the Local authentication provider
	Username string
	// Password is used by the Local authentication provider
	Password string

	// TODO: Permissions
	// Role         string
	// Group        string

	// Templates []Template

	Name  string
	Email string
	Photo string
}

func (u *User) Load(ctx context.Context, db *pg.DB) error {
	if err := db.Model(u).WherePK().Limit(1).Select(); err != nil {
		if errors.Is(err, pg.ErrNoRows) {
			return ErrNotFound
		}

		return fmt.Errorf("load user from db: %w", err)
	}

	return nil
}

func (u *User) LoadWithUsername(ctx context.Context, db *pg.DB) error {
	if err := db.Model(u).
		Where("organization = ?", u.Organization).
		Where("username = ?", u.Username).
		Limit(1).Select(); err != nil {
		if errors.Is(err, pg.ErrNoRows) {
			return ErrNotFound
		}

		return fmt.Errorf("load user from db: %w", err)
	}

	return nil
}
