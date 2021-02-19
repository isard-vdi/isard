package cfg

import (
	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log         cfg.Log
	DB          cfg.DB
	Redis       cfg.Redis
	GraphQL     GraphQL
	ClientsAddr ClientsAddr
}

type ClientsAddr struct {
	Auth string
}

type GraphQL struct {
	Host string
	Port int
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("backend", setDefaults, config)

	return *config
}

func setDefaults() {
	viper.SetDefault("graphql", map[string]interface{}{
		"host": "",
		"port": 1312,
	})

	viper.SetDefault("clientsaddr", map[string]string{
		"auth": "auth:1312",
	})

	cfg.SetDBDefaults()
	cfg.SetRedisDefaults()
}
