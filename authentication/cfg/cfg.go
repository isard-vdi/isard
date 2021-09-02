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
	LDAP   AuthenticationLDAP
	Google AuthenticationGoogle
}

type AuthenticationLDAP struct {
	Protocol      string
	Host          string
	Port          int
	BaseDN        string
	UserSearch    string
	FieldUID      string
	RegexUID      string
	FieldUsername string
	RegexUsername string
	FieldName     string
	RegexName     string
	FieldEmail    string
	RegexEmail    string
	FieldPhoto    string
	RegexPhoto    string
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

	viper.SetDefault("authentication", map[string]interface{}{
		"host":   "",
		"secret": "",
		"local":  true,
		"ldap": map[string]interface{}{
			"protocol":       "ldap",
			"host":           "",
			"port":           389,
			"base_dn":        "",
			"user_search":    "uid=%s",
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
			"client_id":     "",
			"client_secret": "",
		},
	})
}
