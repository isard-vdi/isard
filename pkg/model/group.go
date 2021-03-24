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

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
