package migrations

import (
	"time"

	"github.com/go-pg/migrations/v8"
	"github.com/go-pg/pg/v10/orm"
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

type Entity struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name              string `pg:",notnull"`
	Description       string
	IdentityProviders []*IdentityProvider `pg:"rel:has-many"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

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

type User struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Entities []Entity       `pg:"many2many:isardvdi_user_to_entity"`        // an user has to be in, at least an entity
	Groups   []Group        `pg:"many2many:isardvdi_user_to_group"`         // an user can be at 0+ groups
	Roles    []Role         `pg:"many2many:isardvdi_user_to_role"`          // an user can only have one role per entity
	Quotas   []QuotaProfile `pg:"many2many:isardvdi_user_to_quota_profile"` // an user can only have one quota profile per entity

	AuthConfig string `pg:",notnull,type:jsonb"`

	Name    string `pg:",notnull"`
	Surname string
	Email   string

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

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

type Role struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	EntityID    int               `pg:",notnull"`
	Entity      *Entity           `pg:"rel:has-one"`
	Permissions []*RolePermission `pg:"rel:has-many"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type RolePermission struct {
	RoleID       int   `pg:",pk,notnull"`
	Role         *Role `pg:"rel:has-one"`
	PermissionID int   `pg:",pk,notnull"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type QuotaProfile struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	EntityID    int      `pg:",notnull"`
	Entity      *Entity  `pg:"rel:has-one"`
	Quotas      []*Quota `pg:"rel:has-many"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type Quota struct {
	QuotaProfileID int           `pg:",pk,notnull"`
	QuotaProfile   *QuotaProfile `pg:"rel:has-one"`
	QuotaID        int           `pg:",pk,notnull"`
	Value          string        `pg:",notnull"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

func init() {
	orm.SetTableNameInflector(func(s string) string {
		return "isardvdi_" + s
	})
	orm.RegisterTable(&UserToEntity{})
	orm.RegisterTable(&UserToGroup{})
	orm.RegisterTable(&UserToRole{})
	orm.RegisterTable(&UserToQuotaProfile{})

	// UP
	migrations.MustRegisterTx(func(db migrations.DB) error {
		opt := &orm.CreateTableOptions{FKConstraints: true}
		if err := db.Model(&Entity{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&IdentityProvider{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Role{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&RolePermission{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&QuotaProfile{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Quota{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Group{}).CreateTable(opt); err != nil {
			return err
		}
		if err := db.Model(&User{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&UserToEntity{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&UserToGroup{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&UserToRole{}).CreateTable(opt); err != nil {
			return err
		}

		return db.Model(&UserToQuotaProfile{}).CreateTable(opt)

		// DOWN
	}, func(db migrations.DB) error {
		opt := &orm.DropTableOptions{}

		if err := db.Model(&UserToQuotaProfile{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&UserToRole{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&UserToGroup{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&UserToEntity{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&User{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Group{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Quota{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&QuotaProfile{}).DropTable(opt); err != nil {
			return err
		}
		if err := db.Model(&RolePermission{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Role{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&IdentityProvider{}).DropTable(opt); err != nil {
			return err
		}

		return db.Model(&Entity{}).DropTable(&orm.DropTableOptions{})
	})
}
