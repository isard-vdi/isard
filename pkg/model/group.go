package model

import (
	"context"
	"time"

	"github.com/go-pg/pg/v10"
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

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

var _ pg.BeforeInsertHook = (*Group)(nil)

func (g *Group) BeforeInsert(ctx context.Context) (context.Context, error) {
	g.CreatedAt = time.Now()
	g.UpdatedAt = time.Now()

	return ctx, nil
}

type ExtraGroups struct {
	UserID  int    `pg:",pk,notnull"`
	User    *User  `pg:"rel:has-one"`
	GroupID int    `pg:",pk,notnull"`
	Group   *Group `pg:"rel:has-one"`
	RoleID  int    `pg:",notnull"`
	Role    *Role  `pg:"rel:has-one"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
