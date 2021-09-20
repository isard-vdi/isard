package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log        cfg.Log
	InfluxDB   InfluxDB
	Domain     string
	Collectors Collectors
}

type InfluxDB struct {
	Host   string
	Port   int
	Token  string
	Org    string
	Bucket string
}

type Collectors struct {
	Hypervisor Hypervisor
	System     System
}

type Hypervisor struct {
	Enable     bool
	LibvirtURI string `mapstructure:"libvirt_uri"`
}

type System struct {
	Enable bool
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("stats", setDefaults, config)

	return *config
}

func setDefaults() {
	viper.BindEnv("domain", "DOMAIN")
	viper.BindEnv("influxdb.host", "INFLUXDB_HOST")
	viper.BindEnv("influxdb.token", "INFLUXDB_ADMIN_TOKEN")
	viper.BindEnv("influxdb.org", "STATS_INFLUXDB_ORG")

	viper.SetDefault("influxdb", map[string]interface{}{
		"host":   "",
		"port":   8086,
		"token":  "",
		"org":    "isardvdi",
		"bucket": "isardvdi-go",
	})

	viper.SetDefault("domain", "")

	viper.SetDefault("collectors", map[string]interface{}{
		"hypervisor": map[string]interface{}{
			"enable":      true,
			"libvirt_uri": "qemu+ssh://root@isard-hypervisor:2022/system",
		},
		"system": map[string]interface{}{
			"enable": true,
		},
	})
}
