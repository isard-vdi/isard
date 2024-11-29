package model

import (
	"context"
	"errors"
	"time"

	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/jellydator/ttlcache/v3"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var targetCache = ttlcache.New(
	ttlcache.WithTTL[string, Target](10*time.Second),
	ttlcache.WithDisableTouchOnHit[string, Target](),
)

func init() {
	go targetCache.Start()
}

type Target struct {
	ID        string     `rethinkdb:"id"`
	UserID    string     `rethinkdb:"user_id"`
	DesktopID string     `rethinkdb:"desktop_id"`
	HTTP      TargetHTTP `rethinkdb:"http"`
	SSH       TargetSSH  `rethinkdb:"ssh"`
}

type TargetHTTP struct {
	Enabled   bool `rethinkdb:"enabled"`
	HTTPPort  int  `rethinkdb:"http_port"`
	HTTPSPort int  `rethinkdb:"https_port"`
}

type TargetSSH struct {
	Enabled        bool     `rethinkdb:"enabled"`
	Port           int      `rethinkdb:"port"`
	AuthorizedKeys []string `rethinkdb:"authorized_keys"`
}

func (t *Target) Load(ctx context.Context, sess r.QueryExecutor) error {
	cached := targetCache.Get(t.ID)
	if cached != nil {
		*t = cached.Value()
		return nil
	}

	res, err := r.Table("targets").Get(t.ID).Run(sess)
	if err != nil {
		return &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if err := res.One(t); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return db.ErrNotFound
		}

		return &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	targetCache.Set(t.ID, *t, ttlcache.DefaultTTL)

	return nil
}
