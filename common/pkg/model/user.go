package model

import "time"

type User struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	GroupID int    `pg:",notnull"`
	Group   *Group `pg:"rel:has-one"`

	AuthConfigID int         `pg:",notnull"`
	AuthConfig   *AuthConfig `pg:"rel:has-one"`
	// Local login
	Username string
	Password string

	Name    string `pg:",notnull"`
	Surname string
	Email   string

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
