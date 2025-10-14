package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log  cfg.Log
	GRPC cfg.GRPC
	Maps Maps
}

type Maps struct {
	// SubdomainsPath is the identifier for the subdomains virtual map
	SubdomainsPath string `mapstructure:"subdomains_path"`
	// IndividualPath is the identifier for the individual domains virtual map
	IndividualPath string `mapstructure:"individual_path"`
	// SocketPath is the path to the HAProxy stats socket
	SocketPath string `mapstructure:"socket_path"`
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("haproxy_bastion_sync", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetGRPCDefaults()

	viper.SetDefault("grpc", map[string]interface{}{
		"host": "", // Bind to all interfaces
		"port": 1313,
	})

	viper.SetDefault("maps", map[string]interface{}{
		"subdomains_path": "virt@subdomains",
		"individual_path": "virt@individual",
		"socket_path":     "/var/run/haproxy.sock",
	})
}
