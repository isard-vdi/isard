package model

import (
	"context"
	"errors"
	"time"

	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/jellydator/ttlcache/v3"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var userCache = ttlcache.New(
	ttlcache.WithTTL[string, User](10*time.Second),
	ttlcache.WithDisableTouchOnHit[string, User](),
)

func init() {
	go userCache.Start()
}

type User struct {
	ID         string `rethinkdb:"id"`
	CategoryID string `rethinkdb:"category"`
}

func (u *User) Load(ctx context.Context, sess r.QueryExecutor) error {
	cached := userCache.Get(u.ID)
	if cached != nil {
		*u = cached.Value()
		return nil
	}

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

	userCache.Set(u.ID, *u, ttlcache.DefaultTTL)

	return nil
}
