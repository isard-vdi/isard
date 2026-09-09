package model

import (
	"context"

	"gitlab.com/isard/isardvdi/pkg/db"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Config struct {
	Orchestrator Orchestrator `rethinkdb:"orchestrator"`
}

type Orchestrator struct {
	Enabled bool `rethinkdb:"enabled"`
}

func (c *Config) Load(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("config").Get(1).Field("orchestrator").Run(sess, r.RunOpts{Context: ctx})
	if err != nil {
		return &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if res.IsNil() {
		return db.ErrNotFound
	}

	if err := res.One(&c.Orchestrator); err != nil {
		return &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	return nil
}
