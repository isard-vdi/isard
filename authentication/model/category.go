package model

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/pkg/db"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Category struct {
	ID          string `rethinkdb:"id"`
	Name        string `rethinkdb:"name"`
	Description string `rethinkdb:"description"`
	// TODO: Add Photo field
}

func (c *Category) Exists(ctx context.Context, sess r.QueryExecutor) (bool, error) {
	res, err := r.Table("categories").Get(c.ID).Run(sess)
	if err != nil {
		return false, &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if res.IsNil() {
		return false, nil
	}

	if err := res.One(c); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return false, nil
		}

		return false, &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	return true, nil
}
