package model

import "time"

type Hardware struct {
	ID int

	BaseID     int                  `pg:",notnull"`
	Base       *HardwareBase        `pg:"rel:has-one"`
	Interfaces []*HardwareInterface ``

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

	Name        string `pg:"notnull"`
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
