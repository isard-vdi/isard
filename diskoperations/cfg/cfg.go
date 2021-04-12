package cfg

import (
	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/pkg/cfg"
)

type Cfg struct {
	Log     cfg.Log
	DB      cfg.DB
	GRPC    cfg.GRPC
	Storage Storage
}

type Storage struct {
	Driver   string
	BasePath string
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("diskoperations", setDefaults, config)

	return *config
}

func setDefaults() {
	viper.SetDefault("storage", map[string]string{
		"driver":   "os",
		"basePath": "/opt/isard/disks",
	})

	cfg.SetDBDefaults()
	cfg.SetGRPCDefaults()
}
