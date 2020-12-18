package migrations

import (
	"fmt"

	"github.com/go-pg/migrations/v8"
)

func Run(db migrations.DB) error {
	if _, _, err := migrations.Run(db, "init"); err != nil {
		return fmt.Errorf("initialize db migrations system: %w", err)
	}

	if _, _, err := migrations.Run(db); err != nil {
		return fmt.Errorf("run the db migrations: %w", err)
	}

	return nil
}
