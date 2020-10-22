package cfg

import (
	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/common/pkg/cfg"
)

type Cfg struct {
	Log  cfg.Log
	GRPC GRPC
}

type GRPC struct {
	Host string
	Port int
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("hyper", setDefaults, config)

	return *config
}

func setDefaults() {
	viper.SetDefault("grpc", map[string]interface{}{
		"host": "",
		"port": 1312,
	})
}
