package db

import (
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/pkg/cfg"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var ErrNotFound = errors.New("not found")

func New(cfg cfg.DB) (r.QueryExecutor, error) {
	sess, err := r.Connect(r.ConnectOpts{
		// TOOD: Cluster connections!
		Address:  cfg.Addr(),
		Username: cfg.Usr,
		Password: cfg.Pwd,
		Database: cfg.DB,
	})
	if err != nil {
		return nil, fmt.Errorf("connect to the DB: %w", err)
	}

	return sess, nil
}
