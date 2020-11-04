package cfg

import (
	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/common/pkg/cfg"
)

type Cfg struct {
	Log     cfg.Log
	Redis   Redis
	Libvirt Libvirt
	GRPC    GRPC
}

type Redis struct {
	Host string
	Port int
	Usr  string
	Pwd  string
}

type Libvirt struct {
	URI string
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
	viper.SetDefault("redis", map[string]interface{}{
		"host": "",
		"port": 6379,
		"usr":  "",
		"pwd":  "",
	})
	viper.SetDefault("libvirt", map[string]interface{}{
		"uri": "",
	})
	viper.SetDefault("grpc", map[string]interface{}{
		"host": "",
		"port": 1312,
	})
}
