package model

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/pkg/db"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

// User is an user of IsardVDI
type User struct {
	ID       string `rethinkdb:"id"`
	UID      string `rethinkdb:"uid"`
	Username string `rethinkdb:"username"`
	Provider string `rethinkdb:"provider"`
	Active   bool   `rethinkdb:"active"`

	Category        string   `rethinkdb:"category"`
	Role            Role     `rethinkdb:"role"`
	Group           string   `rethinkdb:"group"`
	SecondaryGroups []string `rethinkdb:"secondary_groups"`

	Password           string `rethinkdb:"password"`
	PasswordResetToken string `rethinkdb:"password_reset_token"`

	Name                   string   `rethinkdb:"name"`
	Email                  string   `rethinkdb:"email"`
	EmailVerified          *float64 `rethinkdb:"email_verified"`
	EmailVerificationToken string   `rethinkdb:"email_verification_token"`
	Photo                  string   `rethinkdb:"photo"`

	DisclaimerAcknowledged bool `rethinkdb:"disclaimer_acknowledged"`

	Accessed float64 `rethinkdb:"accessed"`
}

func (u *User) Load(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("users").Get(u.ID).Run(sess)
	if err != nil {
		return &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if err := res.One(u); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return db.ErrNotFound
		}

		return &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	return nil
}

func (u *User) LoadWithoutID(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("users").Filter(r.And(
		r.Eq(r.Row.Field("uid"), u.UID),
		r.Eq(r.Row.Field("provider"), u.Provider),
		r.Eq(r.Row.Field("category"), u.Category),
	), r.FilterOpts{}).Run(sess)
	if err != nil {
		return &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if err := res.One(u); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return db.ErrNotFound
		}

		return &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	return nil
}

func (u *User) Update(ctx context.Context, sess r.QueryExecutor) error {
	if _, err := r.Table("users").Get(u.ID).Update(u).Run(sess); err != nil {
		return &db.Err{
			Err: err,
		}
	}

	return nil
}

func (u *User) UpdateDisclaimerAcknowledged(ctx context.Context, sess r.QueryExecutor) error {
	if _, err := r.Table("users").Get(u.ID).Update(map[string]interface{}{
		"disclaimer_acknowledged": u.DisclaimerAcknowledged,
	}).Run(sess); err != nil {
		return &db.Err{
			Err: err,
		}
	}

	return nil
}

func (u *User) UpdateEmail(ctx context.Context, sess r.QueryExecutor) error {
	if _, err := r.Table("users").Get(u.ID).Update(map[string]interface{}{
		"email":                    u.Email,
		"email_verified":           u.EmailVerified,
		"email_verification_token": u.EmailVerificationToken,
	}).Run(sess); err != nil {
		return &db.Err{
			Err: err,
		}
	}

	return nil
}

func (u *User) UpdatePasswordResetToken(ctx context.Context, sess r.QueryExecutor) error {
	if _, err := r.Table("users").Get(u.ID).Update(map[string]interface{}{
		"password_reset_token": u.PasswordResetToken,
	}).Run(sess); err != nil {
		return &db.Err{
			Err: err,
		}
	}

	return nil
}

func (u *User) Exists(ctx context.Context, sess r.QueryExecutor) (bool, error) {
	res, err := r.Table("users").Filter(r.And(
		r.Eq(r.Row.Field("uid"), u.UID),
		r.Eq(r.Row.Field("provider"), u.Provider),
		r.Eq(r.Row.Field("category"), u.Category),
	), r.FilterOpts{}).Run(sess)
	if err != nil {
		return false, &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if res.IsNil() {
		return false, nil
	}

	if err := res.One(u); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return false, nil
		}

		return false, &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	return true, nil
}

func (u *User) ExistsWithVerifiedEmail(ctx context.Context, sess r.QueryExecutor) (bool, error) {
	res, err := r.Table("users").Filter(r.And(
		r.Eq(r.Row.Field("category"), u.Category),
		r.Eq(r.Row.Field("email"), u.Email),
		r.Ne(r.Row.Field("email_verified"), nil),
	), r.FilterOpts{}).Run(sess)
	if err != nil {
		return false, &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if err := res.One(u); err != nil {
		if !errors.Is(err, r.ErrEmptyResult) {
			return false, &db.Err{
				Msg: "read db response",
				Err: err,
			}
		}

		return false, nil
	}

	return true, nil
}

func (u *User) ExistsWithPasswordResetToken(ctx context.Context, sess r.QueryExecutor) (bool, error) {
	res, err := r.Table("users").Filter(r.And(
		r.Eq(r.Row.Field("id"), u.ID),
		r.Eq(r.Row.Field("password_reset_token"), u.PasswordResetToken),
	), r.FilterOpts{}).Run(sess)
	if err != nil {
		return false, &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if err := res.One(u); err != nil {
		if !errors.Is(err, r.ErrEmptyResult) {
			return false, &db.Err{
				Msg: "read db response",
				Err: err,
			}
		}

		return false, nil
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

	if u.EmailVerified == nil {
		u.EmailVerified = u2.EmailVerified
	}

	if u.EmailVerificationToken == "" {
		u.EmailVerificationToken = u2.EmailVerificationToken
	}

	if u.Photo == "" {
		u.Photo = u2.Photo
	}

	if u.Accessed == 0 {
		u.Accessed = u2.Accessed
	}
}
