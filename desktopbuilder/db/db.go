package db

import (
	"context"
	"fmt"

	"github.com/go-pg/pg/v10"
	"github.com/go-pg/pg/v10/orm"
	"gitlab.com/isard/isardvdi/common/pkg/model"
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

	if err := initDB(db); err != nil {
		return nil, err
	}

	return db, nil
}

// TODO: Migrations system
func initDB(db *pg.DB) error {
	models := []interface{}{
		(*model.Desktop)(nil),
	}

	for _, model := range models {
		if err := db.Model(model).CreateTable(&orm.CreateTableOptions{
			IfNotExists: true,
		}); err != nil {
			return fmt.Errorf("initialize DB: %w", err)
		}
	}

	return nil
}
