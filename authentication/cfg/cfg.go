package cfg

import (
	"os"
	"time"

	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log            cfg.Log
	DB             cfg.DB
	HTTP           cfg.HTTP
	API            API
	Notifier       Notifier
	Sessions       Sessions
	Authentication Authentication
}

type Authentication struct {
	Host                      string
	Secret                    string
	ImpersonateExpirationTime time.Duration        `mapstructure:"impersonate_expiration_time"`
	Limits                    AuthenticationLimits `mapstructure:"limits"`
	Local                     AuthenticationLocal
	LDAP                      AuthenticationLDAP
	SAML                      AuthenticationSAML
	Google                    AuthenticationGoogle
}

type AuthenticationLimits struct {
	Enabled         bool          `mapstructure:"enabled"`
	MaxAttempts     int           `mapstructure:"max_attempts"`
	RetryAfter      time.Duration `mapstructure:"retry_after"`
	IncrementFactor int           `mapstructure:"increment_factor"`
	MaxTime         time.Duration `mapstructure:"max_time"`
}

type AuthenticationLocal struct {
	Enabled bool
}

type AuthenticationLDAP struct {
	Enabled bool `mapstructure:"enabled"`
}

type AuthenticationSAML struct {
	Enabled bool
}

type AuthenticationGoogle struct {
	Enabled bool
}

type API struct {
	Address string `mapstructure:"address"`
}

type Notifier struct {
	Address string `mapstructure:"address"`
}

type Sessions struct {
	Address string `mapstructure:"address"`
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
		"host":                        getEnv("AUTHENTICATION_AUTHENTICATION_HOST", getEnv("DOMAIN", "localhost")),
		"secret":                      "",
		"impersonate_expiration_time": getEnv("AUTHENTICATION_AUTHENTICATION_IMPERSONATE_EXPIRATION_TIME", "30m"),
		"limits": map[string]interface{}{
			"enabled":          true,
			"max_attempts":     10,
			"retry_after":      "1m",
			"increment_factor": 2,
			"max_time":         "15m",
		},
		"local": map[string]interface{}{
			"enabled": true,
		},
		"ldap": map[string]interface{}{
			"enabled": false,
		},
		"saml": map[string]interface{}{
			"enabled": false,
		},
		"google": map[string]interface{}{
			"enabled": false,
		},
	})

	viper.SetDefault("api", map[string]interface{}{
		"address": "http://isard-api:5000",
	})

	viper.SetDefault("notifier", map[string]interface{}{
		"address": "http://isard-notifier:5000",
	})

	viper.SetDefault("sessions", map[string]interface{}{
		"address": "isard-sessions:1312",
	})
}
