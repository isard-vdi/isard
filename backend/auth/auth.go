package auth

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"

	"github.com/isard-vdi/isard/backend/auth/provider"
	"github.com/isard-vdi/isard/backend/cfg"
	"github.com/isard-vdi/isard/backend/env"
	"github.com/isard-vdi/isard/backend/model"

	"github.com/go-redis/redis"
	"github.com/rbcervilla/redisstore"
)

// Errors that can be returned by IsAuthenticated
var (
	ErrNoSession      = errors.New("not authenticated")
	ErrSessionExpired = errors.New("session expired")
)

func Init(env *env.Env) {
	env.Redis = redis.NewClient(&redis.Options{
		Addr:     fmt.Sprintf("%s:%d", env.Cfg.Redis.Host, env.Cfg.Redis.Port),
		Password: env.Cfg.Redis.Password,
	})

	var err error
	env.Auth.SessStore, err = redisstore.NewRedisStore(env.Redis)
	if err != nil {
		log.Fatalf("connecting to the redis auth store: %v", err)
	}

	noSAML := cfg.AuthSAML{}
	if env.Cfg.Auth.SAML != noSAML {
		env.Auth.SAML, err = provider.NewSAMLProvider(env)
		if err != nil {
			log.Fatalf("setting up the SAML auth provider: %v", err)
		}
	}
}

func IsAuthenticated(ctx context.Context, env *env.Env, c *http.Cookie) (*model.User, error) {
	r := &http.Request{Header: http.Header{}}
	r.AddCookie(c)

	s, err := env.Auth.SessStore.Get(r, provider.SessionStoreKey)
	if err != nil {
		return nil, fmt.Errorf("get session: %w", err)
	}

	if len(s.Values) == 0 {
		return nil, ErrNoSession
	}

	u := &model.User{}
	u.LoadFromID(s.Values[provider.IDStoreKey].(string))

	if err := env.Isard.UserLoad(u); err != nil {
		return nil, err
	}

	p := provider.FromString(s.Values[provider.ProviderStoreKey].(string))
	if err := p.Get(env, u, s.Values[provider.ValueStoreKey]); err != nil {
		// TODO: ErrSessionExpired
		return nil, fmt.Errorf("get user from idp: %w", err)
	}

	if err := env.Isard.UserUpdate(u); err != nil {
		return nil, fmt.Errorf("update user: %v", err)
	}

	return u, nil
}
