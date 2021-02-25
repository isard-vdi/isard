package model

import "time"

type Role struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	EntityID    int               `pg:",notnull"`
	Entity      *Entity           `pg:"rel:has-one"`
	Permissions []*RolePermission `pg:"rel:has-many"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type RolePermission struct {
	RoleID       int   `pg:",pk,notnull"`
	Role         *Role `pg:"rel:has-one"`
	PermissionID int   `pg:",pk,notnull"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
