package cfg

import (
	"gitlab.com/isard/isardvdi/common/pkg/cfg"
)

type Cfg struct {
	Log  cfg.Log
	DB   cfg.DB
	GRPC cfg.GRPC
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("desktopbuilder", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetDBDefaults()
	cfg.SetGRPCDefaults()
}
