package model

import (
	"time"
)

type Group struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	ParentID    int
	Parent      *Group  `pg:"rel:has-one"`
	EntityID    int     `pg:",notnull"`
	Entity      *Entity `pg:"rel:has-one"`
	Name        string  `pg:",notnull"`
	Description string
	Users       []*User `pg:"rel:has-many"`
	// TODO: Is this really required?
	RoleID int
	Role   *Role `pg:"rel:has-one"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type GroupExtra struct {
	UserID  int    `pg:",pk,notnull"`
	User    *User  `pg:"rel:has-one"`
	GroupID int    `pg:",pk,notnull"`
	Group   *Group `pg:"rel:has-one"`
	RoleID  int    `pg:",notnull"`
	Role    *Role  `pg:"rel:has-one"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
