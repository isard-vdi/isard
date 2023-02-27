package cfg

import (
	"time"

	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/pkg/cfg"
)

type Cfg struct {
	Log          cfg.Log
	DB           cfg.DB
	Orchestrator Orchestrator
	DryRun       bool `mapstructure:"infrastructure_dry_run"`
}

type Orchestrator struct {
	PollingInterval   time.Duration `mapstructure:"polling_interval"`
	OperationsTimeout time.Duration `mapstructure:"operations_timeout"`
	OperationsAddress string        `mapstructure:"operations_address"`
	APISecret         string        `mapstructure:"api_secret"`
	Director          string        `mapstructure:"director"`
	DirectorRata      DirectorRata  `mapstructure:"director_rata"`
}

type DirectorRata struct {
	MinCPU       int               `mapstructure:"min_cpu"`
	MinRAM       int               `mapstructure:"min_ram"`
	MaxCPU       int               `mapstructure:"max_cpu"`
	MaxRAM       int               `mapstructure:"max_ram"`
	MinCPUHourly map[time.Time]int `mapstructure:"min_cpu_hourly"`
	MinRAMHourly map[time.Time]int `mapstructure:"min_ram_hourly"`
	HyperMinCPU  int               `mapstructure:"hyper_min_cpu"`
	HyperMinRAM  int               `mapstructure:"hyper_min_ram"`
	HyperMaxCPU  int               `mapstructure:"hyper_max_cpu"`
	HyperMaxRAM  int               `mapstructure:"hyper_max_ram"`
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("orchestrator", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetDBDefaults()

	viper.BindEnv("orchestrator.api_secret", "API_ISARDVDI_SECRET")

	viper.SetDefault("orchestrator", map[string]interface{}{
		"polling_interval":   "30s",
		"operations_timeout": "5m",
		"operations_address": "isard-operations:1312",
		"api_secret":         "",
		"director":           "",
		"director_rata": map[string]interface{}{
			"min_cpu":        0,
			"min_ram":        0,
			"min_cpu_hourly": nil,
			"min_ram_hourly": nil,
			"hyper_min_cpu":  0,
			"hyper_min_ram":  0,
			"hyper_max_cpu":  0,
			"hyper_max_ram":  0,
		},
	})
	viper.SetDefault("infrastructure_dry_run", false)
}
