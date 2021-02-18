package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log      cfg.Log
	Provider string
	Redis    cfg.Redis
	GRPC     cfg.GRPC
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("orchestrator", setDefaults, config)

	return *config
}

func setDefaults() {
	viper.SetDefault("provider", "random")

	cfg.SetRedisDefaults()
	cfg.SetGRPCDefaults()
}
