package db

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/pkg/cfg"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

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

func Ping(ctx context.Context, db r.QueryExecutor) error {
	cur, err := r.Expr(1).Run(db, r.RunOpts{Context: ctx})
	if err != nil {
		return fmt.Errorf("ping the DB: %w", err)
	}
	defer cur.Close()

	var v int
	if err := cur.One(&v); err != nil {
		return fmt.Errorf("ping the DB: %w", err)
	}

	return nil
}
