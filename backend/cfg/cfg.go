package cfg

import (
	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/common/pkg/cfg"
)

type Cfg struct {
	Log     cfg.Log
	DB      cfg.DB
	GraphQL GraphQL
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

	cfg.SetDBDefaults()
}
