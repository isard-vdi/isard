package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log   cfg.Log
	DB    cfg.DB
	Redis cfg.Redis
	GRPC  cfg.GRPC
	HTTP  HTTP
}

type HTTP struct {
	Host string
	Port int
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("auth", setDefaults, config)

	return *config
}

func setDefaults() {
	viper.SetDefault("http", map[string]interface{}{
		"host": "",
		"port": 1313,
	})

	cfg.SetDBDefaults()
	cfg.SetRedisDefaults()
	cfg.SetGRPCDefaults()
}
