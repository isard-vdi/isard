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

type Redis struct {
	Cluster bool
	Host    string
	Port    int
	Usr     string
	Pwd     string
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

func SetRedisDefaults() {
	viper.SetDefault("redis", map[string]interface{}{
		"cluster": false,
		"host":    "",
		"port":    6379,
		"usr":     "",
		"pwd":     "",
	})
}

func SetDBDefaults() {
	viper.SetDefault("db", map[string]interface{}{
		"host": "",
		"port": 5432,
		"usr":  "",
		"pwd":  "",
		"db":   "isard",
	})
}

func SetGRPCDefaults() {
	viper.SetDefault("grpc", map[string]interface{}{
		"host": "",
		"port": 1312,
	})
}
