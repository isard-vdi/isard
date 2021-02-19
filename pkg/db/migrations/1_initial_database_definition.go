package migrations

import (
	"time"

	"github.com/go-pg/migrations/v8"
	"github.com/go-pg/pg/v10/orm"
)

type Entity struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	AuthConfigs []*AuthConfig `pg:"rel:has-many"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type AuthConfig struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	EntityID    int     `pg:",notnull"`
	Entity      *Entity `pg:"rel:has-one"`
	Type        string  `pg:",notnull"`
	Config      string

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type User struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	EntityID int     `pg:",notnull"`
	Entity   *Entity `pg:"rel:has-one"`
	GroupID  int     `pg:",notnull"`
	Group    *Group  `pg:"rel:has-one"`

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

type Role struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	EntityID    int               `pg:",notnull"`
	Entity      *Entity           `pg:"rel:has-one"`
	Permissions []*RolePermission `pg:"rel:has-many"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type RolePermission struct {
	RoleID       int   `pg:",pk,notnull"`
	Role         *Role `pg:"rel:has-one"`
	PermissionID int   `pg:",pk,notnull"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

func init() {
	// UP
	migrations.MustRegisterTx(func(db migrations.DB) error {
		opt := &orm.CreateTableOptions{FKConstraints: true}
		if err := db.Model(&Entity{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&AuthConfig{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Role{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&RolePermission{}).CreateTable(opt); err != nil {
			return err
		}
		if err := db.Model(&Group{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&User{}).CreateTable(opt); err != nil {
			return err
		}

		return db.Model(&ExtraGroups{}).CreateTable(opt)
		// DOWN
	}, func(db migrations.DB) error {
		opt := &orm.DropTableOptions{}
		if err := db.Model(&User{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Group{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&RolePermission{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Role{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&AuthConfig{}).DropTable(opt); err != nil {
			return err
		}

		return db.Model(&Entity{}).DropTable(&orm.DropTableOptions{})
	})
}
