package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"
)

const ServiceName = "migrations"

type Cfg struct {
	Log   cfg.Log
	Redis cfg.Redis
	GRPC  cfg.GRPC
}

func New() Cfg {
	config := &Cfg{}

	cfg.New(ServiceName, setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetRedisDefaults()
	cfg.SetGRPCDefaults()
}
