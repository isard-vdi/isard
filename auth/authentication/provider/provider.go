package provider

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/pkg/model"

	"github.com/go-pg/pg/v10"
	"github.com/gorilla/sessions"
)

var (
	ErrInvalidCredentials = errors.New("invalid credentials")
	ErrNotAuthenticated   = errors.New("not authenticated")
	ErrExpiredToken       = errors.New("the token has expired")
)

type Provider interface {
	Login(ctx context.Context, entityID string, args map[string]interface{}) (string, string, error)
	Logout(ctx context.Context, session *sessions.Session) (string, error)
	Get(ctx context.Context, u *model.User) error
	String() string
}

func FromString(p string, store sessions.Store, db *pg.DB) Provider {
	switch p {
	case provLocal:
		return &Local{store, db}
	default:
		return &Unknown{}
	}
}

var errUnknownIDP = errors.New("unknown identity provider")

type Unknown struct{}

func (Unknown) String() string {
	return "unknown"
}

func (Unknown) Login(context.Context, string, map[string]interface{}) (string, string, error) {
	return "", "", errUnknownIDP
}

func (Unknown) Logout(context.Context, *sessions.Session) (string, error) {
	return "", errUnknownIDP
}

func (Unknown) Get(context.Context, *model.User) error {
	return errUnknownIDP
}
