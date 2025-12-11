package provider

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"slices"
	"strings"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/go-ldap/ldap/v3"
	"github.com/patrickmn/go-cache"
	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var _ Provider = &LDAP{}

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

	AutoRegister      bool   `rethinkdb:"auto_register"`
	AutoRegisterRoles string `rethinkdb:"auto_register_roles"`

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

	RoleAdminIDs    string     `rethinkdb:"role_admin_ids"`
	RoleManagerIDs  string     `rethinkdb:"role_manager_ids"`
	RoleAdvancedIDs string     `rethinkdb:"role_advanced_ids"`
	RoleUserIDs     string     `rethinkdb:"role_user_ids"`
	RoleDefault     model.Role `rethinkdb:"role_default"`

	SaveEmail bool `rethinkdb:"save_email"`
}

type LDAP struct {
	cfg    *LDAPConfig
	secret string
	log    *zerolog.Logger
	db     r.QueryExecutor

	ReUID      *regexp.Regexp
	ReCategory *regexp.Regexp
	ReGroup    *regexp.Regexp
	ReUsername *regexp.Regexp
	ReName     *regexp.Regexp
	ReEmail    *regexp.Regexp
	RePhoto    *regexp.Regexp
	ReRole     *regexp.Regexp

	AutoRegisterRoles []string

	RoleAdminIDs    []string
	RoleManagerIDs  []string
	RoleAdvancedIDs []string
	RoleUserIDs     []string
}

func InitLDAP(secret string, log *zerolog.Logger, db r.QueryExecutor) *LDAP {
	return &LDAP{
		secret: secret,
		log:    log,
		db:     db,
	}
}

func (l *LDAP) LDAPConfig() error {
	l.cfg = &LDAPConfig{}
	if val, found := c.Get("ldap_config"); found {
		l.cfg = val.(*LDAPConfig)
	} else {
		res, err := r.Table("config").Get(1).Field("auth").Field("ldap").Field("ldap_config").Run(l.db)
		if err != nil {
			return &db.Err{
				Err: err,
			}
		}
		if res.IsNil() {
			return db.ErrNotFound
		}
		defer res.Close()
		if err := res.One(l.cfg); err != nil {
			return &db.Err{
				Msg: "read db response",
				Err: err,
			}
		}
		c.Set("ldap_config", l.cfg, cache.DefaultExpiration)
	}

	re, err := regexp.Compile(l.cfg.RegexUID)
	if err != nil {
		l.log.Fatal().Err(err).Msg("invalid UID regex")
	}
	l.ReUID = re

	re, err = regexp.Compile(l.cfg.RegexUsername)
	if err != nil {
		l.log.Fatal().Err(err).Msg("invalid username regex")
	}
	l.ReUsername = re

	re, err = regexp.Compile(l.cfg.RegexName)
	if err != nil {
		l.log.Fatal().Err(err).Msg("invalid name regex")
	}
	l.ReName = re

	re, err = regexp.Compile(l.cfg.RegexEmail)
	if err != nil {
		l.log.Fatal().Err(err).Msg("invalid email regex")
	}
	l.ReEmail = re

	re, err = regexp.Compile(l.cfg.RegexPhoto)
	if err != nil {
		l.log.Fatal().Err(err).Msg("invalid photo regex")
	}
	l.RePhoto = re

	if l.cfg.GuessCategory {
		re, err = regexp.Compile(l.cfg.RegexCategory)
		if err != nil {
			l.log.Fatal().Err(err).Msg("invalid category regex")
		}
		l.ReCategory = re
	}

	if l.cfg.AutoRegister {
		re, err = regexp.Compile(l.cfg.RegexGroup)
		if err != nil {
			l.log.Fatal().Err(err).Msg("invalid group regex")
		}
		l.ReGroup = re

		re, err = regexp.Compile(l.cfg.RoleListRegex)
		if err != nil {
			l.log.Fatal().Err(err).Msg("invalid search group regex")
		}
		l.ReRole = re
	}

	l.AutoRegisterRoles = strings.Split(l.cfg.AutoRegisterRoles, ",")

	l.RoleAdminIDs = strings.Split(l.cfg.RoleAdminIDs, ",")
	l.RoleManagerIDs = strings.Split(l.cfg.RoleManagerIDs, ",")
	l.RoleAdvancedIDs = strings.Split(l.cfg.RoleAdvancedIDs, ",")
	l.RoleUserIDs = strings.Split(l.cfg.RoleUserIDs, ",")

	return nil
}

func (l *LDAP) newConn() (*ldap.Conn, error) {
	if err := l.LDAPConfig(); err != nil {
		return nil, &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}
	conn, err := ldap.DialURL(fmt.Sprintf("%s://%s:%d", l.cfg.Protocol, l.cfg.Host, l.cfg.Port))
	if err != nil {
		return nil, fmt.Errorf("connect to the LDAP server: : %w", err)
	}

	if err := conn.Bind(l.cfg.BindDN, l.cfg.Password); err != nil {
		return nil, fmt.Errorf("bind using the configuration user: %w", err)
	}

	return conn, nil
}

func (l *LDAP) listRoles(usr string) ([]string, error) {
	conn, err := l.newConn()
	if err != nil {
		return nil, err
	}
	defer conn.Close()

	req := ldap.NewSearchRequest(
		l.cfg.RoleListSearchBase,
		ldap.ScopeWholeSubtree,
		ldap.NeverDerefAliases, 0, 0, false,
		fmt.Sprintf(l.cfg.RoleListFilter, ldap.EscapeFilter(usr)),
		[]string{l.cfg.RoleListField},
		nil,
	)

	rsp, err := conn.Search(req)
	if err != nil {
		if ldap.IsErrorWithCode(err, ldap.LDAPResultNoSuchObject) {
			return []string{}, nil
		}

		return nil, fmt.Errorf("get all the user roles: %w", err)
	}

	roles := []string{}
	for _, entry := range rsp.Entries {
		roles = append(roles, entry.GetAttributeValues(l.cfg.RoleListField)...)
	}

	return roles, nil
}

func (l *LDAP) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	usr := *args.FormUsername
	pwd := *args.FormPassword

	conn, err := l.newConn()
	if err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}
	defer conn.Close()

	attributes := []string{"dn", l.cfg.FieldUID, l.cfg.FieldUsername, l.cfg.FieldName, l.cfg.FieldEmail, l.cfg.FieldPhoto}
	if l.cfg.GuessCategory {
		attributes = append(attributes, l.cfg.FieldCategory)
	}
	if l.cfg.AutoRegister {
		attributes = append(attributes, l.cfg.FieldGroup)
	}

	req := ldap.NewSearchRequest(
		l.cfg.BaseSearch,
		ldap.ScopeWholeSubtree,
		ldap.NeverDerefAliases, 0, 0, false,
		fmt.Sprintf(l.cfg.Filter, ldap.EscapeFilter(usr)),
		attributes,
		nil,
	)

	rsp, err := conn.Search(req)
	if err != nil {
		if ldap.IsErrorWithCode(err, ldap.LDAPResultNoSuchObject) {
			return nil, nil, nil, "", "", &ProviderError{
				User:   ErrInvalidCredentials,
				Detail: errors.New("user not found"),
			}
		}

		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("serach the user: %w", err),
		}
	}

	if len(rsp.Entries) != 1 {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInvalidCredentials,
			Detail: fmt.Errorf("user not found: found '%d' users", len(rsp.Entries)),
		}
	}

	entry := rsp.Entries[0]

	usrDN := entry.DN

	if err := conn.Bind(usrDN, pwd); err != nil {
		if ldap.IsErrorWithCode(err, ldap.LDAPResultInvalidCredentials) {
			return nil, nil, nil, "", "", &ProviderError{
				User:   ErrInvalidCredentials,
				Detail: errors.New("invalid password"),
			}
		}

		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("bind the user: %w", err),
		}
	}

	username := matchRegex(l.ReUsername, entry.GetAttributeValue(l.cfg.FieldUsername))
	name := matchRegex(l.ReName, entry.GetAttributeValue(l.cfg.FieldName))
	email := matchRegex(l.ReEmail, entry.GetAttributeValue(l.cfg.FieldEmail))
	photo := matchRegex(l.RePhoto, entry.GetAttributeValue(l.cfg.FieldPhoto))

	u := &types.ProviderUserData{
		Provider: types.ProviderLDAP,
		Category: categoryID,
		UID:      matchRegex(l.ReUID, entry.GetAttributeValue(l.cfg.FieldUID)),

		Username: &username,
		Name:     &name,
		Email:    &email,
		Photo:    &photo,
	}

	if l.cfg.GuessCategory {
		attrCategories := entry.GetAttributeValues(l.cfg.FieldCategory)
		var attrGroups *[]string
		if l.cfg.AutoRegister {
			g := entry.GetAttributeValues(l.cfg.FieldGroup)
			attrGroups = &g
		}

		tkn, err := guessCategory(ctx, l.log, l.db, l.secret, l.ReCategory, attrCategories, attrGroups, nil, u)
		if err != nil {
			return nil, nil, nil, "", "", err
		}

		if tkn != "" {
			return nil, nil, nil, "", tkn, nil
		}
	}

	var g *model.Group
	secondary := []*model.Group{}
	if l.cfg.AutoRegister {
		//
		// Guess group
		//
		attrGroups := entry.GetAttributeValues(l.cfg.FieldGroup)
		if len(attrGroups) == 0 {
			l.log.Debug().Msg("missing groups attribute, will fallback to the default if defined")
		}

		var err *ProviderError
		g, secondary, err = l.GuessGroups(ctx, u, attrGroups)
		if err != nil {
			return nil, nil, nil, "", "", err
		}

		//
		// Guess role
		//
		searchID := usr
		if l.cfg.RoleListUseUserDN {
			searchID = entry.DN
		}

		attrRoles, lErr := l.listRoles(searchID)
		if lErr != nil {
			return nil, nil, nil, "", "", &ProviderError{
				User:   ErrInternal,
				Detail: fmt.Errorf("list all groups: %w", err),
			}
		}

		u.Role, err = l.GuessRole(ctx, u, attrRoles)
		if err != nil {
			return nil, nil, nil, "", "", err
		}
	}

	return g, secondary, u, "", "", nil
}

func (l *LDAP) Callback(context.Context, *token.CallbackClaims, CallbackArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	return nil, nil, nil, "", "", &ProviderError{
		User:   ErrInvalidIDP,
		Detail: errors.New("the LDAP provider doesn't support the callback operation"),
	}
}

func (l *LDAP) AutoRegister(u *model.User) bool {
	if err := l.LDAPConfig(); err != nil {
		return false
	}
	if l.cfg.AutoRegister {
		if len(l.AutoRegisterRoles) != 0 {
			// If the user role is in the autoregister roles list, auto register
			return slices.Contains(l.AutoRegisterRoles, string(u.Role))
		}

		return true
	}

	return false
}

func (l *LDAP) String() string {
	return types.ProviderLDAP
}

func (l *LDAP) Healthcheck() error {
	conn, err := l.newConn()
	if err != nil {
		return fmt.Errorf("unable to connect to the LDAP server: %w", err)
	}

	defer conn.Close()

	return nil
}

func (LDAP) Logout(context.Context, string) (string, error) {
	return "", nil
}

func (l *LDAP) SaveEmail() bool {
	if err := l.LDAPConfig(); err != nil {
		return true
	}
	return l.cfg.SaveEmail
}

func (l *LDAP) GuessGroups(ctx context.Context, u *types.ProviderUserData, rawGroups []string) (*model.Group, []*model.Group, *ProviderError) {
	if err := l.LDAPConfig(); err != nil {
		return nil, nil, &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}
	return guessGroup(ctx, l.db, guessGroupOpts{
		Provider:     l,
		ReGroup:      l.ReGroup,
		DefaultGroup: l.cfg.GroupDefault,
	}, u, rawGroups)
}

func (l *LDAP) GuessRole(ctx context.Context, u *types.ProviderUserData, rawRoles []string) (*model.Role, *ProviderError) {
	if err := l.LDAPConfig(); err != nil {
		return nil, &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}
	return guessRole(guessRoleOpts{
		ReRole:          l.ReRole,
		RoleAdminIDs:    l.RoleAdminIDs,
		RoleManagerIDs:  l.RoleManagerIDs,
		RoleAdvancedIDs: l.RoleAdvancedIDs,
		RoleUserIDs:     l.RoleUserIDs,
		RoleDefault:     l.cfg.RoleDefault,
	}, rawRoles)
}
