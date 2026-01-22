package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log     cfg.Log
	GRPC    cfg.GRPC
	Haproxy Haproxy
}

type Haproxy struct {
	// SocketAddress is the address (path) the HAProxy admin stats socket
	SocketAddress string `mapstructure:"socket_address"`
	// SubdomainsMap is the name of the bastion subdomains virtual map
	SubdomainsMap string `mapstructure:"subdomains_map"`
	// IndividualDomainsMap is the name of the bastion individual domains virtual map
	IndividualDomainsMap string `mapstructure:"individual_domains_map"`
}

type Maps struct {
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("haproxy-bastion-sync", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetGRPCDefaults()

	viper.SetDefault("haproxy", map[string]interface{}{
		"socket_address":         "/var/run/haproxy.sock",
		"subdomains_map":         "virt@subdomains",
		"individual_domains_map": "virt@individual",
	})
}
