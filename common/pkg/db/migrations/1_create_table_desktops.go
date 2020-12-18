package migrations

import (
	"time"

	"github.com/go-pg/migrations/v8"
	"github.com/go-pg/pg/v10/orm"
)

func init() {
	type DesktopOSType int

	type DesktopFirmwareType int

	type DesktopBootType int

	type DesktopTypeBIOS struct {
		FirmwareType DesktopFirmwareType
		OSType       DesktopOSType
		Arch         string
		Machine      string
		Boot         []DesktopBootType
	}

	type DesktopTypeEnum int

	type Desktop struct {
		ID string

		Type     DesktopTypeEnum
		TypeBIOS *DesktopTypeBIOS

		VCPUs uint `pg:"vcpus"`
		RAM   uint // Size in MB

		ExtraXML string

		CreatedAt time.Time
		UpdatedAt time.Time
		DeletedAt time.Time `pg:",soft_delete"`
	}

	// UP
	migrations.MustRegisterTx(func(db migrations.DB) error {
		return db.Model(&Desktop{}).CreateTable(&orm.CreateTableOptions{})

		// DOWN
	}, func(db migrations.DB) error {

		return db.Model(&Desktop{}).DropTable(&orm.DropTableOptions{})
	})
}
