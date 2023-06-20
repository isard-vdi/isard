package cfg

import (
	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/pkg/cfg"
)

type Cfg struct {
	Log   cfg.Log
	GRPC  cfg.GRPC
	Check Check
}

type Check struct {
	Image string
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("check", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetGRPCDefaults()

	viper.SetDefault("check", map[string]interface{}{
		"image": "registry.gitlab.com/isard/isardvdi/check-client:main",
	})
}
