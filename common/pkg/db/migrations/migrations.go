package migrations

import (
	"fmt"

	"github.com/go-pg/migrations/v8"
)

func Run(db migrations.DB) error {
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
