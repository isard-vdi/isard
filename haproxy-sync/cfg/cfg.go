package cfg

import (
	"os"
	"time"

	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log       cfg.Log
	GRPC      cfg.GRPC
	HAProxy   HAProxy
	CertWatch CertWatch `mapstructure:"cert_watch"`
}

type HAProxy struct {
	// SocketAddress is the address (path) the HAProxy admin stats socket
	SocketAddress string `mapstructure:"socket_address"`
	// StartupTimeout is how long to wait for the HAProxy admin socket to become ready at startup
	StartupTimeout time.Duration `mapstructure:"startup_timeout"`

	Domains HAProxyDomains `mapstructure:"domains"`
	Bastion HAProxyBastion `mapstructure:"bastion"`
}

type HAProxyDomains struct {
	// DomainsMap is the name of the domains virtual map
	DomainsMap string `mapstructure:"domains_map"`
	// CrtListPath is the path to the HAProxy crt-list file
	CrtListPath string `mapstructure:"crt_list_path"`
	// CertsPath is the directory where individual PEM certificate files are stored.
	// Each domain gets its own file (<domain>.pem) that is referenced by the crt-list.
	CertsPath string `mapstructure:"certs_path"`
	// BaseDomain is the deployment's own domain, the one the certificate the
	// crt-list already points at is issued for.
	BaseDomain string `mapstructure:"base_domain"`
}

type HAProxyBastion struct {
	// SubdomainsMap is the name of the bastion subdomains virtual map
	SubdomainsMap string `mapstructure:"subdomains_map"`
	// IndividualDomainsMap is the name of the bastion individual domains virtual map
	IndividualDomainsMap string `mapstructure:"individual_domains_map"`
}

type CertWatch struct {
	// Interval is how often the certificates referenced by the crt-list are checked for changes.
	Interval time.Duration `mapstructure:"interval"`
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("haproxy-sync", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetGRPCDefaults()

	viper.SetDefault("haproxy", map[string]any{
		"socket_address":  "/var/run/haproxy.sock",
		"startup_timeout": "120s",
		"domains": map[string]any{
			"domains_map": "virt@domains",
			// crt-list.cfg is the HAProxy crt-list file where domain certificates
			// are registered at runtime for SNI-based selection.
			"crt_list_path": "/certs/crt-list.cfg",
			"certs_path":    "/certs",
			// DOMAIN is what the entrypoint and the configuration use for it.
			"base_domain": os.Getenv("DOMAIN"),
		},
		"bastion": map[string]any{
			"subdomains_map":         "virt@subdomains",
			"individual_domains_map": "virt@individual",
		},
	})

	viper.SetDefault("cert_watch", map[string]any{
		"interval": "60s",
	})
}
