package model

import (
	"context"
	"errors"
	"time"

	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/jellydator/ttlcache/v3"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var categoryCache = ttlcache.New(
	ttlcache.WithTTL[string, Category](10*time.Second),
	ttlcache.WithDisableTouchOnHit[string, Category](),
)

func init() {
	go categoryCache.Start()
}

type Category struct {
	ID            string `rethinkdb:"id"`
	BastionDomain string `rethinkdb:"bastion_domain"` // null: "", false: "0"
}

func (c *Category) Load(ctx context.Context, sess r.QueryExecutor) error {
	cached := categoryCache.Get(c.ID)
	if cached != nil {
		*c = cached.Value()
		return nil
	}

	res, err := r.Table("categories").Get(c.ID).Run(sess)
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

	categoryCache.Set(c.ID, *c, ttlcache.DefaultTTL)

	return nil
}
