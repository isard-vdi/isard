package model

import (
	"time"
)

type Entity struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name              string `pg:",notnull"`
	Description       string
	IdentityProviders []*IdentityProvider `pg:"rel:has-many"`

	Users []*User `pg:"many2many:isardvdi_user_to_entity"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
