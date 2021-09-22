package cfg

import (
	"os"

	"github.com/spf13/viper"
	"gitlab.com/isard/isardvdi/pkg/cfg"
)

type Cfg struct {
	Log            cfg.Log
	DB             cfg.DB
	HTTP           cfg.HTTP
	Authentication Authentication
}

type HTTP struct {
	Host string
	Port int
}

type Authentication struct {
	Host   string
	Secret string
	Local  bool
	Google AuthenticationGoogle
}

type AuthenticationGoogle struct {
	ClientID     string `mapstructure:"client_id"`
	ClientSecret string `mapstructure:"client_secret"`
}

func New() Cfg {
	config := &Cfg{}

	cfg.New("authentication", setDefaults, config)

	return *config
}

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}

func setDefaults() {
	cfg.SetDBDefaults()
	cfg.SetHTTPDefaults()

	viper.BindEnv("authentication.secret", "API_ISARDVDI_SECRET")

	viper.SetDefault("authentication", map[string]interface{}{
		"host":   getEnv("AUTHENTICATION_AUTHENTICATION_HOST", os.Getenv("DOMAIN")),
		"secret": "",
		"local":  true,
		"google": map[string]interface{}{
			"client_id":     "",
			"client_secret": "",
		},
	})
}
