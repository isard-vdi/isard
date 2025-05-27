package model

import (
	"context"
	"errors"
	"time"

	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/jellydator/ttlcache/v3"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var configCache = ttlcache.New(
	ttlcache.WithTTL[int, Config](30*time.Second),
	ttlcache.WithDisableTouchOnHit[int, Config](),
)

func init() {
	go configCache.Start()
}

type Config struct {
	Bastion Bastion `rethinkdb:"bastion"`
}

type Bastion struct {
	Domain                     string `rethinkdb:"domain"`
	Enabled                    bool   `rethinkdb:"enabled"`
	DomainVerificationRequired bool   `rethinkdb:"domain_verification_required"`
}

func (c *Config) Load(ctx context.Context, sess r.QueryExecutor) error {
	cached := configCache.Get(1)
	if cached != nil {
		*c = cached.Value()
		return nil
	}

	res, err := r.Table("config").Get(1).Run(sess)
	if err != nil {
		return &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if err := res.One(c); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return db.ErrNotFound
		}

		return &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	configCache.Set(1, *c, ttlcache.DefaultTTL)

	return nil
}
