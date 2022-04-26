package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log        cfg.Log
	Domain     string
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
	Hypervisor Hypervisor
	Domain     Domain
	System     System
	Socket     Socket
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

func New() Cfg {
	config := &Cfg{}

	cfg.New("stats", setDefaults, config)

	return *config
}

func setDefaults() {
	cfg.SetHTTPDefaults()

	viper.BindEnv("domain", "DOMAIN")

	viper.SetDefault("domain", "")

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
	})
}
