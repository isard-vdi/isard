package cfg

import (
	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/common/pkg/cfg"
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
