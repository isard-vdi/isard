package model

import (
	"context"

	"github.com/go-pg/pg/v10"
	"github.com/go-pg/pg/v10/orm"
)

func init() {
	// Don't pluralize tables and set prefix
	orm.SetTableNameInflector(func(s string) string {
		return "isardvdi_" + s
	})

	orm.RegisterTable(&UserToEntity{})
	orm.RegisterTable(&UserToGroup{})
	orm.RegisterTable(&UserToRole{})
	orm.RegisterTable(&UserToQuotaProfile{})
}

// loadWithUUID loads a model using the UUID
func loadWithUUID(ctx context.Context, db *pg.DB, model interface{}, uuid string) error {
	return db.ModelContext(ctx, model).
		Where("uuid = ?", uuid).
		Limit(1).Select()
}
