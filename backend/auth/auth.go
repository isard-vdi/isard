package auth

import (
	"context"
	"errors"
	"fmt"
	"net/http"

	"gitlab.com/isard/isardvdi/backend/auth/provider"
	"gitlab.com/isard/isardvdi/backend/model"

	"github.com/gorilla/sessions"
)

var (
	ErrNotAuthenticated = errors.New("not authenticated")
)

type Auth struct {
	Store sessions.Store
}

func (a *Auth) GetUser(ctx context.Context, c *http.Cookie) (*model.User, error) {
	r := &http.Request{Header: http.Header{}}
	r.AddCookie(c)

	s, err := a.Store.Get(r, provider.SessionStoreKey)
	if err != nil {
		return nil, fmt.Errorf("get session: %w", err)
	}

	if len(s.Values) == 0 {
		return nil, ErrNotAuthenticated
	}

	u := &model.User{}
	u.FromID()

	// TODO: Update the user in the DB

	return u, nil
}
