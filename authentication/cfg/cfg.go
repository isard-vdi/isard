package cfg

import (
	"os"

	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/spf13/viper"
)

type Cfg struct {
	Log             cfg.Log
	DB              cfg.DB
	HTTP            cfg.HTTP
	Authentication  Authentication
	ShowAdminButton bool `mapstructure:"show_admin_button"`
}

type HTTP struct {
	Host string
	Port int
}

type Authentication struct {
	Host   string
	Secret string
	Local  AuthenticationLocal
	LDAP   AuthenticationLDAP
	Google AuthenticationGoogle
}

type AuthenticationLocal struct {
	Enabled bool
}

type AuthenticationLDAP struct {
	Enabled       bool
	Protocol      string
	Host          string
	Port          int
	BindDN        string `mapstructure:"bind_dn"`
	Password      string
	BaseSearch    string `mapstructure:"base_search"`
	Filter        string
	FieldUID      string `mapstructure:"field_uid"`
	RegexUID      string `mapstructure:"regex_uid"`
	FieldUsername string `mapstructure:"field_username"`
	RegexUsername string `mapstructure:"regex_username"`
	FieldName     string `mapstructure:"field_name"`
	RegexName     string `mapstructure:"regex_name"`
	FieldEmail    string `mapstructure:"field_email"`
	RegexEmail    string `mapstructure:"regex_email"`
	FieldPhoto    string `mapstructure:"field_photo"`
	RegexPhoto    string `mapstructure:"regex_photo"`
}

type AuthenticationGoogle struct {
	Enabled      bool
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
	viper.BindEnv("show_admin_button", "FRONTEND_SHOW_ADMIN_BTN")

	viper.SetDefault("authentication", map[string]interface{}{
		"host":   getEnv("AUTHENTICATION_AUTHENTICATION_HOST", os.Getenv("DOMAIN")),
		"secret": "",
		"local": map[string]interface{}{
			"enabled": true,
		},
		"ldap": map[string]interface{}{
			"enabled":        false,
			"protocol":       "ldap",
			"host":           "",
			"port":           389,
			"bind_dn":        "",
			"password":       "",
			"base_search":    "",
			"filter":         "(&(objectClass=person)(uid=%s))",
			"field_uid":      "",
			"regex_uid":      ".*",
			"field_username": "",
			"regex_username": ".*",
			"field_name":     "",
			"regex_name":     ".*",
			"field_email":    "",
			"regex_email":    ".*",
			"field_photo":    "",
			"regex_photo":    ".*",
		},
		"google": map[string]interface{}{
			"enabled":       false,
			"client_id":     "",
			"client_secret": "",
		},
	})

	viper.SetDefault("show_admin_button", true)
}
