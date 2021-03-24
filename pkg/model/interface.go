package model

import "time"

type Interface struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	// TODO: Should this belong to an entity?
	NetworkID      int           `pg:",notnull"`
	Network        *Network      `pg:"rel:has-one"`
	InterfaceQOSId int           `pg:",notnull"`
	InterfaceQOS   *InterfaceQOS `pg:"rel:has-one"`

	Name        string `pg:",notnull"`
	Description string
	Config      string `pg:",notnull"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type InterfaceQOS struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	Config      string `pg:",notnull"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
