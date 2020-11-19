package cfg

import (
	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/common/pkg/cfg"
)

type Cfg struct {
	Log                cfg.Log
	GRPC               cfg.GRPC
	DesktopBuilderAddr string
	OrchestratorAddr   string
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("controller", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetGRPCDefaults()

	viper.SetDefault("desktopbuilderaddr", "desktopbuilder:1312")
	viper.SetDefault("orchestratoraddr", "orchestrator:1312")
}
