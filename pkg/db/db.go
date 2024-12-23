package db

import (
	"fmt"

	"gitlab.com/isard/isardvdi/pkg/cfg"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func New(cfg cfg.DB) (r.QueryExecutor, error) {
	fmt.Println(cfg.Usr)
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
