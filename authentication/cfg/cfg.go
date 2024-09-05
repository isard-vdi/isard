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
	Host          string
	Secret        string
	TokenDuration time.Duration        `mapstructure:"token_duration"`
	Limits        AuthenticationLimits `mapstructure:"limits"`
	Local         AuthenticationLocal
	LDAP          AuthenticationLDAP
	SAML          AuthenticationSAML
	Google        AuthenticationGoogle
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

	Protocol   string `mapstructure:"protocol"`
	Host       string `mapstructure:"host"`
	Port       int    `mapstructure:"port"`
	BindDN     string `mapstructure:"bind_dn"`
	Password   string `mapstructure:"password"`
	BaseSearch string `mapstructure:"base_search"`

	Filter        string `mapstructure:"filter"`
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

	RoleListSearchBase string `mapstructure:"role_list_search_base"`
	RoleListFilter     string `mapstructure:"role_list_filter"`
	RoleListUseUserDN  bool   `mapstructure:"role_list_use_user_dn"`
	RoleListField      string `mapstructure:"role_list_field"`
	RoleListRegex      string `mapstructure:"role_list_regex"`

	RoleAdminIDs    []string   `mapstructure:"role_admin_ids"`
	RoleManagerIDs  []string   `mapstructure:"role_manager_ids"`
	RoleAdvancedIDs []string   `mapstructure:"role_advanced_ids"`
	RoleUserIDs     []string   `mapstructure:"role_user_ids"`
	RoleDefault     model.Role `mapstructure:"role_default"`
}

type AuthenticationSAML struct {
	Enabled bool

	MetadataURL string `mapstructure:"metadata_url"`
	KeyFile     string `mapstructure:"key_file"`
	CertFile    string `mapstructure:"cert_file"`

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
		"host":           getEnv("AUTHENTICATION_AUTHENTICATION_HOST", getEnv("DOMAIN", "localhost")),
		"secret":         "",
		"token_duration": "4h",
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
			"enabled":               false,
			"protocol":              "ldap",
			"host":                  "",
			"port":                  389,
			"bind_dn":               "",
			"password":              "",
			"base_search":           "",
			"filter":                "(&(objectClass=person)(uid=%s))",
			"field_uid":             "",
			"regex_uid":             ".*",
			"field_username":        "",
			"regex_username":        ".*",
			"field_name":            "",
			"regex_name":            ".*",
			"field_email":           "",
			"regex_email":           ".*",
			"field_photo":           "",
			"regex_photo":           ".*",
			"auto_register":         false,
			"auto_register_roles":   []string{},
			"guess_category":        false,
			"field_category":        "",
			"regex_category":        ".*",
			"field_group":           "",
			"regex_group":           ".*",
			"group_default":         "default",
			"role_list_search_base": "",
			"role_list_filter":      "(&(objectClass=posixGroup)(memberUid=%s))",
			"role_list_use_user_dn": false,
			"role_list_field":       "",
			"role_list_regex":       ".*",
			"role_admin_ids":        []string{},
			"role_manager_ids":      []string{},
			"role_advanced_ids":     []string{},
			"role_user_ids":         []string{},
			"role_default":          "user",
		},
		"saml": map[string]interface{}{
			"enabled":             false,
			"metadata_url":        "",
			"key_file":            "/keys/isardvdi.key",
			"cert_file":           "/keys/isardvdi.cert",
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
