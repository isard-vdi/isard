package model

import "time"

type Template struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	// TODO: Should all the names be unique?
	Name        string `pg:",notnull"`
	Description string
	HardwareID  int       `pg:",notnull"`
	Hardware    *Hardware `pg:"rel:has-one"`
	UserID      int       `pg:",notnull"`
	User        *User     `pg:"rel:has-one"`
	EntityID    int       `pg:",notnull"`
	Entity      *Entity   `pg:"rel:has-one"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
