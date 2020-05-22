package cfg

import (
	"errors"
	"strings"

	"github.com/spf13/viper"
	"go.uber.org/zap"
)

// Cfg holds all the configuration for the disk-operations
type Cfg struct {
	GRPC GRPC `mapstruct:"grpc"`
}

// GRPC holds the configuration for the GRPC server
type GRPC struct {
	Port int `mapstruct:"port"`
}

func Init(sugar *zap.SugaredLogger) Cfg {
	setDefaults()

	if err := viper.ReadInConfig(); err != nil {
		if !errors.As(err, &viper.ConfigFileNotFoundError{}) {
			sugar.Fatalw("read configuration",
				"err", err,
			)
		}

		sugar.Warn("configuration file not found, using environment values and defaults")
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
	viper.SetConfigName("disk-operations")

	viper.AddConfigPath(".")
	viper.AddConfigPath("$HOME/.isard")
	viper.AddConfigPath("$HOME/.config/isard")
	viper.AddConfigPath("/etc/isard")

	viper.SetDefault("grpc", map[string]interface{}{
		"port": 1312,
	})

	viper.SetEnvPrefix("DISK_OPERATIONS")
	viper.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	viper.AutomaticEnv()
}
