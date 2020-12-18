package provider

import (
	"errors"
	"net/http"

	"github.com/go-pg/pg/v10"
	"github.com/gorilla/sessions"
	"gitlab.com/isard/isardvdi/backend/model"
)

var ErrInvalidCredentials = errors.New("invalid credentials")

const (
	SessionStoreKey  = "session"
	UsrIDStoreKey    = "id"
	ProviderStoreKey = "provider"
)

type Provider interface {
	Get(u *model.User) error
	Login(w http.ResponseWriter, r *http.Request) error
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

func (Unknown) Login(w http.ResponseWriter, r *http.Request) error {
	return errUnknownIDP
}

func (Unknown) Get(u *model.User) error {
	return errUnknownIDP
}
