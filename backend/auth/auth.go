package auth

import (
	"context"
	"errors"
	"fmt"
	"net/http"

	"gitlab.com/isard/isardvdi/backend/auth/provider"
	"gitlab.com/isard/isardvdi/backend/model"

	"github.com/go-pg/pg/v10"
	"github.com/go-redis/redis/v8"
	"github.com/gorilla/sessions"
	"github.com/rbcervilla/redisstore/v8"
)

var (
	ErrNotAuthenticated = errors.New("not authenticated")
)

type Auth struct {
	Store sessions.Store
	DB    *pg.DB
}

func New(ctx context.Context, redis redis.UniversalClient, db *pg.DB) (*Auth, error) {
	store, err := redisstore.NewRedisStore(ctx, redis)
	if err != nil {
		return nil, fmt.Errorf("create redis sessions store: %w", err)
	}

	return &Auth{
		Store: store,
		DB:    db,
	}, nil
}

func (a *Auth) GetUser(ctx context.Context, c *http.Cookie) (*model.User, error) {
	r := &http.Request{Header: http.Header{}}
	r.AddCookie(c)

	s, err := a.Store.Get(r, provider.SessionStoreKey)
	if err != nil {
		return nil, fmt.Errorf("get session: %w", err)
	}

	val := NewStoreValues(s.Values)

	if val.Len() == 0 {
		return nil, ErrNotAuthenticated
	}

	u := &model.User{
		ID: val.UsrID(),
	}

	// TODO: Load user

	p := provider.FromString(val.Provider(), a.Store, a.DB)
	if err := p.Get(u); err != nil {
		// TODO: Session expired
		return nil, fmt.Errorf("get user from identity provider: %w", err)
	}

	// TODO: Update the user in the DB

	return u, nil
}
