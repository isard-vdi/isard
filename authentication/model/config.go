package model

import (
	"context"

	"gitlab.com/isard/isardvdi/pkg/db"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Config struct {
	Local  Local  `rethinkdb:"local"`
	LDAP   LDAP   `rethinkdb:"ldap"`
	SAML   SAML   `rethinkdb:"saml"`
	Google Google `rethinkdb:"google"`
}

type Local struct {
	Enabled bool `rethinkdb:"enabled"`
}

type LDAP struct {
	Enabled    bool       `rethinkdb:"enabled"`
	LDAPConfig LDAPConfig `rethinkdb:"ldap_config"`
}

type LDAPConfig struct {
	Protocol   string `rethinkdb:"protocol"`
	Host       string `rethinkdb:"host"`
	Port       int    `rethinkdb:"port"`
	BindDN     string `rethinkdb:"bind_dn"`
	Password   string `rethinkdb:"password"`
	BaseSearch string `rethinkdb:"base_search"`

	Filter        string `rethinkdb:"filter"`
	FieldUID      string `rethinkdb:"field_uid"`
	RegexUID      string `rethinkdb:"regex_uid"`
	FieldUsername string `rethinkdb:"field_username"`
	RegexUsername string `rethinkdb:"regex_username"`
	FieldName     string `rethinkdb:"field_name"`
	RegexName     string `rethinkdb:"regex_name"`
	FieldEmail    string `rethinkdb:"field_email"`
	RegexEmail    string `rethinkdb:"regex_email"`
	FieldPhoto    string `rethinkdb:"field_photo"`
	RegexPhoto    string `rethinkdb:"regex_photo"`

	AutoRegister      bool                `rethinkdb:"auto_register"`
	AutoRegisterRoles db.CommaSplitString `rethinkdb:"auto_register_roles"`

	GuessCategory bool   `rethinkdb:"guess_category"`
	FieldCategory string `rethinkdb:"field_category"`
	RegexCategory string `rethinkdb:"regex_category"`

	FieldGroup   string `rethinkdb:"field_group"`
	RegexGroup   string `rethinkdb:"regex_group"`
	GroupDefault string `rethinkdb:"group_default"`

	RoleListSearchBase string `rethinkdb:"role_list_search_base"`
	RoleListFilter     string `rethinkdb:"role_list_filter"`
	RoleListUseUserDN  bool   `rethinkdb:"role_list_use_user_dn"`
	RoleListField      string `rethinkdb:"role_list_field"`
	RoleListRegex      string `rethinkdb:"role_list_regex"`

	RoleAdminIDs    db.CommaSplitString `rethinkdb:"role_admin_ids"`
	RoleManagerIDs  db.CommaSplitString `rethinkdb:"role_manager_ids"`
	RoleAdvancedIDs db.CommaSplitString `rethinkdb:"role_advanced_ids"`
	RoleUserIDs     db.CommaSplitString `rethinkdb:"role_user_ids"`
	RoleDefault     Role                `rethinkdb:"role_default"`

	SaveEmail bool `rethinkdb:"save_email"`

	AllowInsecureTLS bool `rethinkdb:"allow_insecure_tls"`
}

type SAML struct {
	Enabled    bool       `rethinkdb:"enabled"`
	SAMLConfig SAMLConfig `rethinkdb:"saml_config"`
}

type SAMLConfig struct {
	MetadataURL     string      `rethinkdb:"metadata_url"`
	MetadataFile    string      `rethinkdb:"metadata_file"`
	EntityID        string      `rethinkdb:"entity_id"`
	SignatureMethod string      `rethinkdb:"signature_method"`
	KeyFile         string      `rethinkdb:"key_file"`
	CertFile        string      `rethinkdb:"cert_file"`
	MaxIssueDelay   db.Duration `rethinkdb:"max_issue_delay"`

	FieldUID      string `rethinkdb:"field_uid"`
	RegexUID      string `rethinkdb:"regex_uid"`
	FieldUsername string `rethinkdb:"field_username"`
	RegexUsername string `rethinkdb:"regex_username"`
	FieldName     string `rethinkdb:"field_name"`
	RegexName     string `rethinkdb:"regex_name"`
	FieldEmail    string `rethinkdb:"field_email"`
	RegexEmail    string `rethinkdb:"regex_email"`
	FieldPhoto    string `rethinkdb:"field_photo"`
	RegexPhoto    string `rethinkdb:"regex_photo"`

	AutoRegister      bool                `rethinkdb:"auto_register"`
	AutoRegisterRoles db.CommaSplitString `rethinkdb:"auto_register_roles"`

	GuessCategory bool   `rethinkdb:"guess_category"`
	FieldCategory string `rethinkdb:"field_category"`
	RegexCategory string `rethinkdb:"regex_category"`

	FieldGroup   string `rethinkdb:"field_group"`
	RegexGroup   string `rethinkdb:"regex_group"`
	GroupDefault string `rethinkdb:"group_default"`

	FieldRole       string              `rethinkdb:"field_role"`
	RegexRole       string              `rethinkdb:"regex_role"`
	RoleAdminIDs    db.CommaSplitString `rethinkdb:"role_admin_ids"`
	RoleManagerIDs  db.CommaSplitString `rethinkdb:"role_manager_ids"`
	RoleAdvancedIDs db.CommaSplitString `rethinkdb:"role_advanced_ids"`
	RoleUserIDs     db.CommaSplitString `rethinkdb:"role_user_ids"`
	RoleDefault     Role                `rethinkdb:"role_default"`

	LogoutRedirectURL string `rethinkdb:"logout_redirect_url"`

	SaveEmail bool `rethinkdb:"save_email"`

	AllowInsecureTLS bool `rethinkdb:"allow_insecure_tls"`
}

type Google struct {
	Enabled      bool         `rethinkdb:"enabled"`
	GoogleConfig GoogleConfig `rethinkdb:"google_config"`
}

type GoogleConfig struct {
	ClientID     string `rethinkdb:"client_id"`
	ClientSecret string `rethinkdb:"client_secret"`
}

func (c *Config) Load(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("config").Get(1).Field("auth").Run(sess, r.RunOpts{Context: ctx})
	if err != nil {
		return &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if res.IsNil() {
		return db.ErrNotFound
	}

	if err := res.One(c); err != nil {
		return &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	return nil
}
