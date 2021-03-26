package model

import "github.com/go-pg/pg/v10/orm"

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
