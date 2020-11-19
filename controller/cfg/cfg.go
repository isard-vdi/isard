package cfg

import (
	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/common/pkg/cfg"
)

type Cfg struct {
	Log         cfg.Log
	GRPC        cfg.GRPC
	ClientsAddr ClientsAddr
}

type ClientsAddr struct {
	DesktopBuilder string
	Orchestrator   string
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("controller", setDefaults, config)

	return *config
}

func setDefaults() {
	viper.SetDefault("clientsaddr", map[string]interface{}{
		"desktopbuilder": "desktopbuilder:1312",
		"orchestrator":   "orchestrator:1312",
	})

	cfg.SetGRPCDefaults()
}
