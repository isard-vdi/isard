package cfg

import (
	"os"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
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

	MetadataURL     string        `mapstructure:"metadata_url"`
	MetadataFile    string        `mapstructure:"metadata_file"`
	EntityID        string        `mapstructure:"entity_id"`
	SignatureMethod string        `mapstructure:"signature_method"`
	KeyFile         string        `mapstructure:"key_file"`
	CertFile        string        `mapstructure:"cert_file"`
	MaxIssueDelay   time.Duration `mapstructure:"max_issue_delay"`

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

	AutoRegister      bool     `mapstructure:"auto_register"`
	AutoRegisterRoles []string `mapstructure:"auto_register_roles"`

	GuessCategory bool   `mapstructure:"guess_category"`
	FieldCategory string `mapstructure:"field_category"`
	RegexCategory string `mapstructure:"regex_category"`

	FieldGroup   string `mapstructure:"field_group"`
	RegexGroup   string `mapstructure:"regex_group"`
	GroupDefault string `mapstructure:"group_default"`

	FieldRole       string     `mapstructure:"field_role"`
	RegexRole       string     `mapstructure:"regex_role"`
	RoleAdminIDs    []string   `mapstructure:"role_admin_ids"`
	RoleManagerIDs  []string   `mapstructure:"role_manager_ids"`
	RoleAdvancedIDs []string   `mapstructure:"role_advanced_ids"`
	RoleUserIDs     []string   `mapstructure:"role_user_ids"`
	RoleDefault     model.Role `mapstructure:"role_default"`

	LogoutRedirectURL string `mapstructure:"logout_redirect_url"`
	SaveEmail         bool   `mapstructure:"save_email"`
}

type AuthenticationGoogle struct {
	Enabled      bool
	ClientID     string `mapstructure:"client_id"`
	ClientSecret string `mapstructure:"client_secret"`
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
			"enabled":             false,
			"metadata_url":        "",
			"metadata_file":       "/keys/idp-metadata.xml",
			"entity_id":           "",
			"signature_method":    "",
			"key_file":            "/keys/isardvdi.key",
			"cert_file":           "/keys/isardvdi.cert",
			"max_issue_delay":     "90s",
			"field_uid":           "",
			"regex_uid":           ".*",
			"field_username":      "",
			"regex_username":      ".*",
			"field_name":          "",
			"regex_name":          ".*",
			"field_email":         "",
			"regex_email":         ".*",
			"field_photo":         "",
			"regex_photo":         ".*",
			"auto_register":       false,
			"auto_register_roles": []string{},
			"guess_category":      false,
			"field_category":      "",
			"regex_category":      ".*",
			"field_group":         "",
			"regex_group":         ".*",
			"group_default":       "default",
			"field_role":          "",
			"regex_role":          ".*",
			"role_admin_ids":      []string{},
			"role_manager_ids":    []string{},
			"role_advanced_ids":   []string{},
			"role_user_ids":       []string{},
			"role_default":        "user",
			"logout_redirect_url": "",
			"save_email":          true,
		},
		"google": map[string]interface{}{
			"enabled":       false,
			"client_id":     "",
			"client_secret": "",
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
