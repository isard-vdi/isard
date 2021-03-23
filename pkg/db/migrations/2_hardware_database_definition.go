package migrations

import (
	"time"

	"github.com/go-pg/migrations/v8"
	"github.com/go-pg/pg/v10/orm"
)

type Hardware struct {
	ID int

	BaseID int           `pg:",notnull"`
	Base   *HardwareBase `pg:"rel:has-one"`

	// Resources
	Interfaces []*HardwareInterface `pg:"rel:has-many"`
	Disks      []*HardwareDisk      `pg:"rel:has-many"`

	BootOrder []BootType
	VCPUs     int `pg:"vcpus,notnull"`
	Memory    int `pg:",notnull"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}
type BootType int

type HardwareBase struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	OS          string `pg:",notnull"`
	OSVariant   string
	XML         string `pg:",notnull"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type HardwareInterface struct {
	InterfaceID int        `pg:",pk,notnull"`
	Interface   *Interface `pg:"rel:has-one"`
	HardwareID  int        `pg:",pk,notnull"`
	Hardware    *Hardware  `pg:"rel:has-one"`

	MAC   string `pg:",notnull"`
	Order int

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type HardwareDisk struct {
	DiskID     int       `pg:",pk,notnull"`
	Disk       *Disk     `pg:"rel:has-one"`
	HardwareID int       `pg:",pk,notnull"`
	Hardware   *Hardware `pg:"rel:has-one"`

	Order    int
	ReadOnly bool
	// Config   string

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
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
	UserID      int       `pg:",notnull"`
	User        *User     `pg:"rel:has-one"`
	EntityID    int       `pg:",notnull"`
	Entity      *Entity   `pg:"rel:has-one"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type Desktop struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	HardwareID  int       `pg:",notnull"`
	Hardware    *Hardware `pg:"rel:has-one"`
	UserID      int       `pg:",notnull"`
	User        *User     `pg:"rel:has-one"`
	EntityID    int       `pg:",notnull"`
	Entity      *Entity   `pg:"rel:has-one"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type Disk struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Type     DiskType `pg:",notnull"`
	ParentID int
	Parent   *Disk   `pg:"rel:has-one"`
	EntityID int     `pg:",notnull"`
	Entity   *Entity `pg:"rel:has-one"`
	UserID   int     `pg:",notnull"`
	User     *User   `pg:"rel:has-one"`
	// TODO: Size?

	Name        string `pg:",notnull"`
	Description string

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type DiskType int

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

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type InterfaceQOS struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	Config      string `pg:",notnull"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
	DeletedAt time.Time `pg:",soft_delete"`
}

type Network struct {
	ID   int
	UUID string `pg:",notnull,unique"`

	Name        string `pg:",notnull"`
	Description string
	Config      string `pg:",notnull"`

	CreatedAt time.Time `pg:"default:now(),notnull"`
	UpdatedAt time.Time `pg:"default:now(),notnull"`
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

		if err := db.Model(&HardwareDisk{}).CreateTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Template{}).CreateTable(opt); err != nil {
			return err
		}

		return db.Model(&Desktop{}).CreateTable(opt)

		// DOWN
	}, func(db migrations.DB) error {
		opt := &orm.DropTableOptions{}
		if err := db.Model(&Desktop{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Template{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&HardwareDisk{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&HardwareInterface{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Disk{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Hardware{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&HardwareBase{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&Interface{}).DropTable(opt); err != nil {
			return err
		}

		if err := db.Model(&InterfaceQOS{}).DropTable(opt); err != nil {
			return err
		}

		return db.Model(&Network{}).DropTable(&orm.DropTableOptions{})
	})
}
