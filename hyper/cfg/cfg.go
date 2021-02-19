package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log     cfg.Log
	Redis   cfg.Redis
	Libvirt Libvirt
	GRPC    cfg.GRPC
}

type Libvirt struct {
	URI string
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("hyper", setDefaults, config)

	return *config
}

func setDefaults() {
	viper.SetDefault("libvirt", map[string]interface{}{
		"uri": "",
	})

	cfg.SetRedisDefaults()
	cfg.SetGRPCDefaults()
}
