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
	// SubdomainsPath is the path to the subdomains map file
	SubdomainsPath string `mapstructure:"subdomains_path"`
	// IndividualPath is the path to the individual domains map file
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
		"subdomains_path": "/usr/local/etc/haproxy/bastion_domains/subdomains.map",
		"individual_path": "/usr/local/etc/haproxy/bastion_domains/individual.map",
		"socket_path":     "/var/run/haproxy.sock",
	})
}
