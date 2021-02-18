package authentication

import (
	"context"
	"errors"
	"fmt"
	"time"

	"gitlab.com/isard/isardvdi/auth/authentication/provider"
	"gitlab.com/isard/isardvdi/auth/authentication/store"

	"github.com/go-pg/pg/v10"
	"github.com/go-redis/redis/v8"
	"github.com/gorilla/sessions"
	"github.com/rbcervilla/redisstore/v8"
)

type Interface interface {
	Login(ctx context.Context, provider string, entityID string, args map[string]interface{}) (string, string, error)
	Logout(ctx context.Context, token string) (string, error)
	Check(ctx context.Context, token string) (string, error)
	Refresh(ctx context.Context, token string) (string, error)
}

type Authentication struct {
	db    *pg.DB
	store sessions.Store
}

func New(ctx context.Context, redis redis.UniversalClient, db *pg.DB) (*Authentication, error) {
	store, err := redisstore.NewRedisStore(ctx, redis)
	if err != nil {
		return nil, fmt.Errorf("create redis sessions store: %w", err)
	}

	return &Authentication{
		store: store,
		db:    db,
	}, nil
}

func (a *Authentication) Login(ctx context.Context, p string, entityID string, args map[string]interface{}) (token, redirect string, err error) {
	provider := provider.FromString(p, a.store, a.db)
	return provider.Login(ctx, entityID, args)
}

func (a *Authentication) Logout(ctx context.Context, token string) (string, error) {
	r := store.BuildHTTPRequest(ctx, token)
	session, err := a.store.Get(r, store.SessionStoreKey)
	if err != nil {
		return "", fmt.Errorf("get the session: %w", err)
	}

	if session.IsNew {
		return "", provider.ErrNotAuthenticated
	}

	values := store.NewStoreValues(session.Values)
	provider := provider.FromString(values.Provider(), a.store, a.db)

	redirect, err := provider.Logout(ctx, session)
	if err != nil {
		return "", fmt.Errorf("log out: %w", err)
	}

	return redirect, nil
}

func (a *Authentication) Check(ctx context.Context, token string) (string, error) {
	fmt.Println(token)
	r := store.BuildHTTPRequest(ctx, token)
	session, err := a.store.Get(r, store.SessionStoreKey)
	if err != nil {
		return "", fmt.Errorf("get the session: %w", err)
	}

	if session.IsNew {
		return "", provider.ErrNotAuthenticated
	}

	values := store.NewStoreValues(session.Values)
	// TODO: Change token lifespan
	if values.Time().Add(1 * time.Hour).Before(time.Now()) {
		return values.UsrID(), provider.ErrExpiredToken
	}

	return values.UsrID(), nil
}

func (a *Authentication) Refresh(ctx context.Context, token string) (string, error) {
	return "", errors.New("not implemented yet")
}
