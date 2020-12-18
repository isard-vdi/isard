package db

import (
	"context"

	"gitlab.com/isard/isardvdi/common/pkg/db/migrations"

	"github.com/go-pg/pg/v10"
)

func New(addr, usr, pwd, name string) (*pg.DB, error) {
	db := pg.Connect(&pg.Options{
		Addr:     addr,
		User:     usr,
		Password: pwd,
		Database: name,
	})

	if err := db.Ping(context.Background()); err != nil {
		return nil, err
	}

	if err := migrations.Run(db); err != nil {
		return nil, err
	}

	return db, nil
}
