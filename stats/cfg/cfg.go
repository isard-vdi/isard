package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log        cfg.Log
	Domain     string
	Flavour    string
	HTTP       cfg.HTTP
	LibvirtURI string `mapstructure:"libvirt_uri"`
	SSH        SSH
	Collectors Collectors
}

type SSH struct {
	Host string
	Port int
	User string
}

type Collectors struct {
	Hypervisor             Hypervisor
	Domain                 Domain
	System                 System
	Socket                 Socket
	IsardVDIAPI            IsardVDIAPI            `mapstructure:"isardvdi_api"`
	IsardVDIAuthentication IsardvdiAuthentication `mapstructure:"isardvdi_authentication"`
}

type Hypervisor struct {
	Enable bool
}

type Domain struct {
	Enable bool
}

type System struct {
	Enable bool
}

type Socket struct {
	Enable bool
}

type IsardVDIAPI struct {
	Enable bool
	Addr   string
	Secret string
}

type IsardvdiAuthentication struct {
	Enable      bool
	LokiAddress string `mapstructure:"loki_address"`
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("stats", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetHTTPDefaults()

	viper.BindEnv("domain", "DOMAIN")
	viper.BindEnv("flavour", "FLAVOUR")
	viper.BindEnv("collectors.isardvdi_api.secret", "API_ISARDVDI_SECRET")
	viper.BindEnv("collectors.isardvdi_authentication.loki_address", "LOKI_ADDRESS")

	viper.SetDefault("domain", "")
	viper.SetDefault("flavour", "all-in-one")

	viper.SetDefault("http", map[string]interface{}{
		"port": "9091",
	})

	viper.SetDefault("libvirt_uri", "qemu+ssh://root@isard-hypervisor:2022/system")

	viper.SetDefault("ssh", map[string]interface{}{
		"host": "isard-hypervisor",
		"port": 2022,
		"user": "root",
	})

	viper.SetDefault("collectors", map[string]interface{}{
		"hypervisor": map[string]interface{}{
			"enable": true,
		},
		"domain": map[string]interface{}{
			"enable": true,
		},
		"system": map[string]interface{}{
			"enable": true,
		},
		"socket": map[string]interface{}{
			"enable": true,
		},
		"isardvdi_api": map[string]interface{}{
			"enable": true,
			"addr":   "http://isard-api:5000",
			"secret": "",
		},
		"isardvdi_authentication": map[string]interface{}{
			"enable":       true,
			"loki_address": "http://isard-loki:3100",
		},
	})
}
