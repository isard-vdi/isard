package model

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/pkg/db"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Secret struct {
	ID         string `rethinkdb:"id"`
	CategoryID string `rethinkdb:"category_id"`
	Secret     string `rethinkdb:"secret"`
}

func (s *Secret) Load(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("secrets").Get(s.ID).Run(sess)
	if err != nil {
		return &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if err := res.One(s); err != nil {
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
