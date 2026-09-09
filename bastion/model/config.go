package model

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/pkg/db"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Config struct {
	Bastion Bastion `rethinkdb:"bastion"`
}

type Bastion struct {
	Domain                     string `rethinkdb:"domain"`
	Enabled                    bool   `rethinkdb:"enabled"`
	DomainVerificationRequired bool   `rethinkdb:"domain_verification_required"`
}

func (c *Config) Load(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("config").Get(1).Run(sess, r.RunOpts{Context: ctx})
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

	return nil
}
