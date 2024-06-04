package cfg

import (
	"time"

	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/pkg/cfg"
)

type Cfg struct {
	Log         cfg.Log
	HTTP        cfg.HTTP
	APIAddr     string        `mapstructure:"api_addr"`
	IdleTimeout time.Duration `mapstructure:"idle_timeout"`
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("rdpgw", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetHTTPDefaults()

	viper.SetDefault("api_addr", "isard-api:5000")
	viper.SetDefault("idle_timeout", "30m")
}
