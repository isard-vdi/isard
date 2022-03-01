package model

import (
	"context"
	"errors"
	"fmt"
	"strings"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

const idsFieldSeparator = "-"

var ErrNotFound = errors.New("not found")

// User is an user of IsardVDI
type User struct {
	UID      string `rethinkdb:"uid"`
	Username string `rethinkdb:"username"`
	Password string `rethinkdb:"password"`
	Provider string `rethinkdb:"provider"`
	Active   bool   `rethinkdb:"active"`

	Category string `rethinkdb:"category"`
	Role     Role   `rethinkdb:"role"`
	Group    string `rethinkdb:"group"`

	Name  string `rethinkdb:"name"`
	Email string `rethinkdb:"email"`
	Photo string `rethinkdb:"photo"`

	Accessed float64 `rethinkdb:"accessed"`
}

func (u *User) Load(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("users").Get(u.ID()).Run(sess)
	if err != nil {
		return err
	}
	defer res.Close()

	if err := res.One(u); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return ErrNotFound
		}

		return fmt.Errorf("read db response: %w", err)
	}

	return nil
}

func (u *User) Update(ctx context.Context, sess r.QueryExecutor) error {
	_, err := r.Table("users").Get(u.ID()).Update(u).Run(sess)
	return err
}

func (u *User) ID() string {
	return strings.Join([]string{u.Provider, u.Category, u.UID, u.Username}, idsFieldSeparator)
}

func UserFromID(id string) *User {
	parts := strings.Split(id, idsFieldSeparator)

	return &User{
		Provider: parts[0],
		Category: parts[1],
		UID:      parts[2],
		Username: parts[3],
	}
}

func (u *User) Exists(ctx context.Context, sess r.QueryExecutor) (bool, error) {
	res, err := r.Table("users").Get(u.ID()).Run(sess)
	if err != nil {
		return false, err
	}
	defer res.Close()

	if res.IsNil() {
		return false, nil
	}

	if err := res.One(u); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return false, ErrNotFound
		}

		return false, fmt.Errorf("read db response: %w", err)
	}

	return true, nil
}

func (u *User) LoadWithoutOverride(u2 *User) {
	if u.Category == "" {
		u.Category = u2.Category
	}

	if u.Role == "" {
		u.Role = u2.Role
	}

	if u.Group == "" {
		u.Group = u2.Group
	}

	if u.Name == "" {
		u.Name = u2.Name
	}

	if u.Email == "" {
		u.Email = u2.Email
	}

	if u.Photo == "" {
		u.Photo = u2.Photo
	}

	if u.Accessed == 0 {
		u.Accessed = u2.Accessed
	}
}
