package migrations

import (
	"fmt"

	"github.com/go-pg/migrations/v8"
	"github.com/go-pg/pg/v10/orm"
)

func Run(db migrations.DB) error {
	// Don't pluralize tables
	orm.SetTableNameInflector(func(s string) string {
		return s
	})

	old, new, err := migrations.Run(db, "init")
	if err != nil {
		return fmt.Errorf("initialize db migrations system: %w", err)
	}

	fmt.Printf("migrated from %d to %d\n", old, new)

	old, new, err = migrations.Run(db)
	if err != nil {
		return fmt.Errorf("run the db migrations: %w", err)
	}

	fmt.Printf("migrated from %d to %d\n", old, new)

	return nil
}
