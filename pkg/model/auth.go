package model

import (
	"time"

	"github.com/mitchellh/mapstructure"
)

type IdentityProvider struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	EntityID    int     `pg:",notnull"`
	Entity      *Entity `pg:"rel:has-one"`
	Type        string  `pg:",notnull"`
	Config      string

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type AuthConfig interface{}

type AuthConfigLocal struct {
	Usr string `json:"usr"`
	Pwd string `json:"pwd"`
}

func GenerateAuthConfigLocal(a AuthConfig) *AuthConfigLocal {
	cfg := &AuthConfigLocal{}
	mapstructure.Decode(a, cfg)

	return cfg
}
