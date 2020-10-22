package cfg

import (
	"errors"
	"strings"

	"github.com/rs/zerolog/log"
	"github.com/spf13/viper"
)

type Log struct {
	Level string
}

func New(name string, setDefaults func(), target interface{}) {
	viper.SetConfigName(strings.ToLower(name))

	viper.AddConfigPath(".")
	viper.AddConfigPath("$HOME/.isard")
	viper.AddConfigPath("$HOME/.config/isard")
	viper.AddConfigPath("/etc/isard")

	setCommonDefaults()
	setDefaults()

	viper.SetEnvPrefix(strings.ToUpper(name))
	viper.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	viper.AutomaticEnv()

	if err := viper.ReadInConfig(); err != nil {
		if !errors.As(err, &viper.ConfigFileNotFoundError{}) {
			log.Fatal().Err(err).Msg("read configuration")
		}

		log.Warn().Msg("configuration file not found, using environment variables and defaults")
	}

	if err := viper.Unmarshal(target); err != nil {
		log.Fatal().Err(err).Msg("unmarshal configuration")
	}

}

func setCommonDefaults() {
	viper.SetDefault("log", map[string]interface{}{
		"level": "info",
	})

}
