package cfg

import (
	"errors"
	"fmt"
	"strings"

	"github.com/rs/zerolog/log"
	"github.com/spf13/viper"
)

type Log struct {
	Level string
}

type DB struct {
	Host string
	Port int
	Usr  string
	Pwd  string
	DB   string
}

func (d *DB) Addr() string {
	return fmt.Sprintf("%s:%d", d.Host, d.Port)
}

type GRPC struct {
	Host string
	Port int
}

func (g *GRPC) Addr() string {
	return fmt.Sprintf("%s:%d", g.Host, g.Port)
}

type HTTP struct {
	Host string
	Port int
}

func (h *HTTP) Addr() string {
	return fmt.Sprintf("%s:%d", h.Host, h.Port)
}

func New(name string, setDefaults func(), target interface{}) {
	viper.SetConfigName(strings.ToLower(name))

	viper.AddConfigPath(".")
	viper.AddConfigPath("$HOME/.isardvdi")
	viper.AddConfigPath("$HOME/.config/isardvdi")
	viper.AddConfigPath("/etc/isardvdi")

	setCommonDefaults()
	setDefaults()

	viper.SetEnvPrefix(strings.ToUpper(name))
	viper.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	viper.AutomaticEnv()

	if err := viper.ReadInConfig(); err != nil {
		if !errors.As(err, &viper.ConfigFileNotFoundError{}) {
			log.Fatal().Str("service", name).Err(err).Msg("read configuration")
		}

		log.Warn().Str("service", name).Msg("Configuration file not found, using environment variables and defaults")
	}

	if err := viper.Unmarshal(target); err != nil {
		log.Fatal().Str("service", name).Err(err).Msg("unmarshal configuration")
	}

}

func setCommonDefaults() {
	viper.BindEnv("log.level", "LOG_LEVEL")

	viper.SetDefault("log", map[string]interface{}{
		"level": "info",
	})
}

func SetDBDefaults() {
	viper.SetDefault("db", map[string]interface{}{
		"host": "isard-db",
		"port": 28015,
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

func SetHTTPDefaults() {
	viper.SetDefault("http", map[string]interface{}{
		"host": "",
		"port": 1313,
	})
}
