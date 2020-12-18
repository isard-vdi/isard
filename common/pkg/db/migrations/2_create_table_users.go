package migrations

import (
	"time"

	"github.com/go-pg/migrations/v8"
	"github.com/go-pg/pg/v10/orm"
)

func init() {
	type User struct {
		ID           string
		Provider     string
		Organization string

		// Username is used by the Local authentication provider
		Username string
		// Password is used by the Local authentication provider
		Password string

		// TODO: Permissions
		// Role         string
		// Group        string

		// Templates []Template

		Name  string
		Email string
		Photo string

		CreatedAt time.Time
		UpdatedAt time.Time
		DeletedAt time.Time `pg:",soft_delete"`
	}

	// UP
	migrations.MustRegisterTx(func(db migrations.DB) error {
		return db.Model(&User{}).CreateTable(&orm.CreateTableOptions{})

		// DOWN
	}, func(db migrations.DB) error {

		return db.Model(&User{}).DropTable(&orm.DropTableOptions{})
	})
}
