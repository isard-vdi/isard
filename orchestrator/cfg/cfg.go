package cfg

import (
	"errors"
	"strings"

	"github.com/spf13/viper"
	"go.uber.org/zap"
)

type Cfg struct {
	Redis Redis `mapstructure:"redis"`
}

type Redis struct {
	Host     string `mapstructure:"host"`
	Port     int    `mapstructure:"port"`
	Password string `mapstructure:"password"`
}

func Init(sugar *zap.SugaredLogger) Cfg {
	setDefaults()

	if err := viper.ReadInConfig(); err != nil {
		if !errors.As(err, &viper.ConfigFileNotFoundError{}) {
			sugar.Fatalw("read configuration",
				"err", err,
			)
		}

		sugar.Info("configuration file not found, using environment values and defaults")
	}

	cfg := Cfg{}
	if err := viper.Unmarshal(&cfg); err != nil {
		sugar.Fatalw("unmarshal configuration",
			"err", err,
		)
	}

	return cfg
}

func setDefaults() {
	viper.SetConfigName("orchestrator")

	viper.AddConfigPath(".")
	viper.AddConfigPath("$HOME/.isard")
	viper.AddConfigPath("$HOME/.config/isard")
	viper.AddConfigPath("/etc/isard")

	viper.SetDefault("redis", map[string]interface{}{
		"host":     "redis",
		"port":     6379,
		"password": "",
	})

	viper.SetEnvPrefix("ORCHESTRATOR")
	viper.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	viper.AutomaticEnv()
}
