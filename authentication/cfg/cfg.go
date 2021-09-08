package cfg

import (
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
	UserShowAdminButton string
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

func setDefaults() {
	cfg.SetDBDefaults()
	cfg.SetHTTPDefaults()

	viper.BindEnv("authentication.secret", "API_ISARDVDI_SECRET")
	viper.BindEnv("authentication.user_show_admin_button", "USER_FRONTEND_SHOW_ADMIN_BTN")

	viper.SetDefault("authentication", map[string]interface{}{
		"host":   "",
		"secret": "",
		"local":  true,
		"google": map[string]interface{}{
			"client_id":     "",
			"client_secret": "",
		},
		"user_show_admin_button": "false",
	})
}
