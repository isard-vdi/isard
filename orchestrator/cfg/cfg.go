package cfg

import (
	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/common/pkg/cfg"
)

type Cfg struct {
	Log      cfg.Log
	Provider string
	Redis    Redis
	GRPC     GRPC
}

type Redis struct {
	Host string
	Port int
	Usr  string
	Pwd  string
}

type GRPC struct {
	Host string
	Port int
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("orchestrator", setDefaults, config)

	return *config
}

func setDefaults() {
	viper.SetDefault("provider", "random")
	viper.SetDefault("redis", map[string]interface{}{
		"host": "",
		"port": 6379,
		"usr":  "",
		"pwd":  "",
	})
	viper.SetDefault("grpc", map[string]interface{}{
		"host": "",
		"port": 1312,
	})
}
