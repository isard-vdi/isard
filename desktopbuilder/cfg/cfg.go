package cfg

import (
	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/common/pkg/cfg"
)

type Cfg struct {
	Log  cfg.Log
	DB   DB
	GRPC GRPC
}

type DB struct {
	Host string
	Port int
	Usr  string
	Pwd  string
	DB   string
}

type GRPC struct {
	Host string
	Port int
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("desktopbuilder", setDefaults, config)

	return *config
}

func setDefaults() {
	viper.SetDefault("db", map[string]interface{}{
		"host": "",
		"port": 5432,
		"usr":  "",
		"pwd":  "",
		"db":   "isard",
	})
	viper.SetDefault("grpc", map[string]interface{}{
		"host": "",
		"port": 1312,
	})
}
