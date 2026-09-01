package model

import (
	"context"
	"errors"
	"time"

	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/jellydator/ttlcache/v3"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var deploymentCache = ttlcache.New(
	ttlcache.WithTTL[string, Deployment](30*time.Second),
	ttlcache.WithDisableTouchOnHit[string, Deployment](),
)

func init() {
	go deploymentCache.Start()
}

type Deployment struct {
	ID       string   `rethinkdb:"id"`
	UserID   string   `rethinkdb:"user"`
	CoOwners []string `rethinkdb:"co_owners"`
}

func (d *Deployment) Load(ctx context.Context, sess r.QueryExecutor) error {
	cached := deploymentCache.Get(d.ID)
	if cached != nil {
		*d = cached.Value()
		return nil
	}

	res, err := r.Table("deployments").Get(d.ID).Run(sess, r.RunOpts{Context: ctx})
	if err != nil {
		return &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if err := res.One(d); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return db.ErrNotFound
		}

		return &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	deploymentCache.Set(d.ID, *d, ttlcache.DefaultTTL)

	return nil
}
