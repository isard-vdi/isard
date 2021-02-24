package migrations

import (
	"errors"
	"time"

	"github.com/go-pg/migrations/v8"
	"github.com/go-pg/pg/v10/orm"
)

type Hardware struct {
	ID int

	BaseID     int                  `pg:",notnull"`
	Base       *HardwareBase        `pg:"rel:has-one"`
	Interfaces []*HardwareInterface `pg:"rel:has-many"`

	VCPUs     int     `pg:",notnull"`
	MemoryMin int     `pg:",notnull"`
	MemoryMax int     `pg:",notnull"`
	Disks     []*Disk `pg:"rel:has-many"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type HardwareBase struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	OS          string `pg:",notnull"`
	OSVariant   string
	XML         string `pg:",notnull"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type HardwareInterface struct {
	InterfaceID int        `pg:",pk,notnull"`
	Interface   *Interface `pg:"rel:has-one"`
	HardwareID  int        `pg:",pk,notnull"`

	MAC   string `pg:",notnull"`
	Order int

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type Template struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	// TODO: Should all the names be unique?
	Name        string `pg:",notnull"`
	Description string
	HardwareID  int       `pg:",notnull"`
	Hardware    *Hardware `pg:"rel:has-one"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

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

type Disk struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	ParentID   int       `pg:",notnull"`
	Parent     *Disk     `pg:"rel:has-one"`
	HardwareID int       `pg:",notnull"`
	Hardware   *Hardware `pg:"rel:has-one"`

	Type     DiskType `pg:",notnull"`
	Path     string   `pg:",notnull"`
	Enable   bool
	ReadOnly bool
	Order    int
	Config   string

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type DiskType int

const (
	DiskTypeUnknown DiskType = iota
	DiskTypeQcow2
	DiskTypeRaw
)

type Interface struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	NetworkID      int           `pg:",notnull"`
	Network        *Network      `pg:"rel:has-one"`
	InterfaceQOSId int           `pg:",notnull"`
	InterfaceQOS   *InterfaceQOS `pg:"rel:has-one"`

	Name        string `pg:",notnull"`
	Description string
	Config      string `pg:",notnull"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type InterfaceQOS struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	Config      string `pg:",notnull"`

	CreatedAt time.Time `pg:",notnull"`
	UpdatedAt time.Time `pg:",notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

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

func init() {
	// UP
	migrations.MustRegisterTx(func(db migrations.DB) error {
		opt := &orm.CreateTableOptions{FKConstraints: true}
		if err := db.Model(&Network{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&InterfaceQOS{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Interface{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&HardwareBase{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Hardware{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Disk{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&HardwareInterface{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Template{}).CreateTable(opt); err != nil {
			return err
		}

		return db.Model(&Desktop{}).CreateTable(opt)

		// DOWN
	}, func(db migrations.DB) error {
		return errors.New("not implamented")
	})
}
