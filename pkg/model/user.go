package model

import (
	"context"
	"fmt"
	"time"

	"github.com/go-pg/pg/v10"
	"github.com/go-pg/pg/v10/orm"
)

type User struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Entities []*Entity       `pg:"many2many:isardvdi_user_to_entity"`        // an user has to be in, at least an entity
	Groups   []*Group        `pg:"many2many:isardvdi_user_to_group"`         // an user can be at 0+ groups
	Roles    []*Role         `pg:"many2many:isardvdi_user_to_role"`          // an user can only have one role per entity
	Quotas   []*QuotaProfile `pg:"many2many:isardvdi_user_to_quota_profile"` // an user can only have one quota profile per entity

	AuthConfig map[string]AuthConfig `pg:",notnull,type:jsonb"`

	Name    string `pg:",notnull"`
	Surname string
	Email   string

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

func (u *User) Load(ctx context.Context, db *pg.DB) error {
	if err := db.Model(u).
		WherePK().
		Limit(1).Select(); err != nil {
		return fmt.Errorf("load user from db: %w", err)
	}

	return nil
}

func (u *User) LoadWithUUID(ctx context.Context, db *pg.DB) error {
	if err := db.Model(u).
		Where("uuid = ?", u.UUID).
		Limit(1).Select(); err != nil {
		return fmt.Errorf("load user from db: %w", err)
	}

	return nil
}

func (u *User) LoadWithAuthLocal(ctx context.Context, db *pg.DB, entityUUID, usr string) (string, error) {
	i := &IdentityProvider{}
	if err := db.Model(i).Column("identity_provider.uuid").Relation("Entity.uuid", func(q *orm.Query) (*orm.Query, error) {
		return q.Where("entity.uuid = ?", entityUUID).Where("identity_provider.type = 'local'"), nil
	}).Select(); err != nil {
		return "", fmt.Errorf("load entity provider from db: %w", err)
	}

	e := &Entity{}
	if err := db.Model(e).Relation("Users", func(q *orm.Query) (*orm.Query, error) {
		return q.Where(`auth_config -> ? ->> 'usr' = ?`, i.UUID, usr).Limit(1), nil
	}).Where("uuid = ?", entityUUID).Select(); err != nil {
		return "", fmt.Errorf("load user from db: %w", err)
	}

	if len(e.Users) == 0 {
		return "", fmt.Errorf("load user from db: %w", pg.ErrNoRows)
	}

	*u = *e.Users[0]
	u.Entities = append(u.Entities, e)

	return i.UUID, nil
}

// func (u *User) LoadWithUsername(ctx context.Context, db *pg.DB, entityUUID string) error {
// 	if err := db.Model(u).
// 		Relation("Entity").
// 		Where("entity.uuid = ?", entityUUID).
// 		Where("username = ?", u.Username).
// 		Limit(1).Select(); err != nil {
// 		return fmt.Errorf("load user from db: %w", err)
// 	}

// 	return nil
// }

type UserToEntity struct {
	UserID   int     `pg:",pk"`
	User     *User   `pg:"rel:has-one"`
	EntityID int     `pg:",pk"`
	Entity   *Entity `pg:"rel:has-one"`
}

type UserToGroup struct {
	UserID  int    `pg:",pk"`
	User    *User  `pg:"rel:has-one"`
	GroupID int    `pg:",pk"`
	Group   *Group `pg:"rel:has-one"`
}

type UserToRole struct {
	UserID int   `pg:",pk"`
	User   *User `pg:"rel:has-one"`
	RoleID int   `pg:",pk"`
	Role   *Role `pg:"rel:has-one"`
}

type UserToQuotaProfile struct {
	UserID         int           `pg:",pk"`
	User           *User         `pg:"rel:has-one"`
	QuotaProfileID int           `pg:",pk"`
	QuotaProfile   *QuotaProfile `pg:"rel:has-one"`
}
