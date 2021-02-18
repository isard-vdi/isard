package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
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
