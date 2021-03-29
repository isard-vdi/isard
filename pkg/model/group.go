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

	Users []*User `pg:"many2many:isardvdi_user_to_group"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
