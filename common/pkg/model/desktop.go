package model

import "time"

type Desktop struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	HardwareID  int       `pg:",notnull"`
	Hardware    *Hardware `pg:"rel:has-one"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
