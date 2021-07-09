package model

import (
	"context"
	"errors"
	"fmt"
	"strings"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

const userIDSFieldSeparator = "-"

var ErrNotFound = errors.New("not found")

// User is an user of IsardVDI
type User struct {
	UID      string `rethinkdb:"uid"`
	Username string `rethinkdb:"username"`
	Password string `rethinkdb:"password"`
	Provider string `rethinkdb:"provider"`

	Category string `rethinkdb:"category"`
	Role     string `rethinkdb:"role"`
	Group    string `rethinkdb:"group"`

	Name  string `rethinkdb:"name"`
	Email string `rethinkdb:"email"`
	Photo string `rethinkdb:"photo"`
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

func (u *User) ID() string {
	return strings.Join([]string{u.Provider, u.Category, u.UID, u.Username}, userIDSFieldSeparator)
}

func (u *User) Exists(ctx context.Context, sess r.QueryExecutor) (bool, error) {
	res, err := r.Table("users").Get(u.ID()).Run(sess)
	if err != nil {
		return false, err
	}
	defer res.Close()

	return !res.IsNil(), nil
}
