package model

import "time"

type Network struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	Config      string `pg:",notnull"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
