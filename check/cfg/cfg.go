package cfg

import "gitlab.com/isard/isardvdi/pkg/cfg"

type Cfg struct {
	Log  cfg.Log
	GRPC cfg.GRPC
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("check", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetGRPCDefaults()
}
