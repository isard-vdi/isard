package cfg

import (
	"time"

	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/pkg/cfg"
)

type Cfg struct {
	Log          cfg.Log
	Orchestrator Orchestrator
	DryRun       bool `mapstructure:"dry_run"`
}

type Orchestrator struct {
	PollingInterval   time.Duration `mapstructure:"polling_interval"`
	OperationsTimeout time.Duration `mapstructure:"operations_timeout"`
	OperationsAddress string        `mapstructure:"operations_address"`
	CheckAddress      string        `mapstructure:"check_address"`
	APIAddress        string        `mapstructure:"api_address"`
	APISecret         string        `mapstructure:"api_secret"`
	Director          string        `mapstructure:"director"`
	DirectorRata      DirectorRata  `mapstructure:"director_rata"`
	Check             Check         `mapstructure:"check"`
}

type DirectorRata struct {
	MinCPU       int               `mapstructure:"min_cpu"`
	MinRAM       int               `mapstructure:"min_ram"`
	MinCPUHourly map[time.Time]int `mapstructure:"min_cpu_hourly"`
	MinRAMHourly map[time.Time]int `mapstructure:"min_ram_hourly"`
	MaxCPU       int               `mapstructure:"max_cpu"`
	MaxRAM       int               `mapstructure:"max_ram"`
	MaxCPUHourly map[time.Time]int `mapstructure:"max_cpu_hourly"`
	MaxRAMHourly map[time.Time]int `mapstructure:"max_ram_hourly"`
	HyperMinCPU  int               `mapstructure:"hyper_min_cpu"`
	HyperMinRAM  int               `mapstructure:"hyper_min_ram"`
	HyperMaxCPU  int               `mapstructure:"hyper_max_cpu"`
	HyperMaxRAM  int               `mapstructure:"hyper_max_ram"`
}

type Check struct {
	Enabled             bool   `mapstructure:"enabled"`
	TemplateID          string `mapstructure:"template_id"`
	FailMaintenanceMode bool   `mapstructure:"fail_maintenance_mode"`
	FailSelfSigned      bool   `mapstructure:"fail_self_signed"`
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("orchestrator", setDefaults, config)

	return *config
}

func setDefaults() {
	viper.BindEnv("orchestrator.api_secret", "API_ISARDVDI_SECRET")
	viper.BindEnv("dry_run", "INFRASTRUCTURE_DRY_RUN")

	viper.SetDefault("orchestrator", map[string]interface{}{
		"polling_interval":   "30s",
		"operations_timeout": "5m",
		"operations_address": "isard-operations:1312",
		"check_address":      "isard-check:1312",
		"api_address":        "http://isard-api:5000",
		"api_secret":         "",
		"director":           "",
		"director_rata": map[string]interface{}{
			"min_cpu":        0,
			"min_ram":        0,
			"min_cpu_hourly": nil,
			"min_ram_hourly": nil,
			"max_cpu":        0,
			"max_ram":        0,
			"max_cpu_hourly": nil,
			"max_ram_hourly": nil,
			"hyper_min_cpu":  0,
			"hyper_min_ram":  0,
			"hyper_max_cpu":  0,
			"hyper_max_ram":  0,
		},
		"check": map[string]interface{}{
			"enabled":               true,
			"template_id":           "",
			"fail_maintenance_mode": true,
			"fail_self_signed":      true,
		},
	})
	viper.SetDefault("dry_run", false)
}
