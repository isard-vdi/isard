package provider

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"regexp"
	"slices"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"

	"github.com/go-ldap/ldap/v3"
	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var _ ConfigurableProvider[model.LDAPConfig] = &LDAP{}

type LDAPConfig struct {
	Protocol   string
	Host       string
	Port       int
	BindDN     string
	Password   string
	BaseSearch string

	Filter        string
	FieldUID      string
	ReUID         *regexp.Regexp
	FieldUsername string
	ReUsername    *regexp.Regexp
	FieldName     string
	ReName        *regexp.Regexp
	FieldEmail    string
	ReEmail       *regexp.Regexp
	FieldPhoto    string
	RePhoto       *regexp.Regexp

	AutoRegister      bool
	AutoRegisterRoles []string

	GuessCategory bool
	FieldCategory string
	ReCategory    *regexp.Regexp

	FieldGroup   string
	ReGroup      *regexp.Regexp
	GroupDefault string

	RoleListSearchBase string
	RoleListFilter     string
	RoleListUseUserDN  bool
	RoleListField      string
	ReRole             *regexp.Regexp

	RoleAdminIDs    []string
	RoleManagerIDs  []string
	RoleAdvancedIDs []string
	RoleUserIDs     []string
	RoleDefault     model.Role

	SaveEmail bool

	AllowInsecureTLS bool
}

type LDAP struct {
	cfg *cfgManager[LDAPConfig]

	secret string
	log    *zerolog.Logger
	db     r.QueryExecutor
}

func InitLDAP(secret string, log *zerolog.Logger, db r.QueryExecutor) *LDAP {
	return &LDAP{
		cfg:    &cfgManager[LDAPConfig]{cfg: &LDAPConfig{}},
		secret: secret,
		log:    log,
		db:     db,
	}
}

func (l *LDAP) LoadConfig(_ context.Context, cfg model.LDAPConfig) error {
	prvCfg := l.cfg.Cfg()

	prvCfg.Protocol = cfg.Protocol
	prvCfg.Host = cfg.Host
	prvCfg.Port = cfg.Port
	prvCfg.BindDN = cfg.BindDN
	prvCfg.Password = cfg.Password
	prvCfg.BaseSearch = cfg.BaseSearch

	prvCfg.Filter = cfg.Filter
	prvCfg.FieldUID = cfg.FieldUID
	re, err := regexp.Compile(cfg.RegexUID)
	if err != nil {
		return fmt.Errorf("invalid UID regex: %w", err)
	}

	prvCfg.ReUID = re

	prvCfg.FieldUsername = cfg.FieldUsername
	re, err = regexp.Compile(cfg.RegexUsername)
	if err != nil {
		return fmt.Errorf("invalid username regex: %w", err)
	}

	prvCfg.ReUsername = re

	prvCfg.FieldName = cfg.FieldName
	re, err = regexp.Compile(cfg.RegexName)
	if err != nil {
		return fmt.Errorf("invalid name regex: %w", err)
	}

	prvCfg.ReName = re

	prvCfg.FieldEmail = cfg.FieldEmail
	re, err = regexp.Compile(cfg.RegexEmail)
	if err != nil {
		return fmt.Errorf("invalid email regex: %w", err)
	}

	prvCfg.ReEmail = re

	prvCfg.FieldPhoto = cfg.FieldPhoto
	re, err = regexp.Compile(cfg.RegexPhoto)
	if err != nil {
		return fmt.Errorf("invalid photo regex: %w", err)
	}

	prvCfg.RePhoto = re

	prvCfg.AutoRegister = cfg.AutoRegister
	prvCfg.AutoRegisterRoles = cfg.AutoRegisterRoles

	prvCfg.GuessCategory = cfg.GuessCategory
	prvCfg.FieldCategory = cfg.FieldCategory
	if cfg.GuessCategory {
		re, err = regexp.Compile(cfg.RegexCategory)
		if err != nil {
			return fmt.Errorf("invalid category regex: %w", err)
		}

		prvCfg.ReCategory = re

	} else {
		prvCfg.ReCategory = nil
	}

	prvCfg.FieldGroup = cfg.FieldGroup
	prvCfg.GroupDefault = cfg.GroupDefault

	prvCfg.RoleListSearchBase = cfg.RoleListSearchBase
	prvCfg.RoleListFilter = cfg.RoleListFilter
	prvCfg.RoleListUseUserDN = cfg.RoleListUseUserDN
	prvCfg.RoleListField = cfg.RoleListField

	if cfg.AutoRegister {
		re, err = regexp.Compile(cfg.RegexGroup)
		if err != nil {
			return fmt.Errorf("invalid group regex: %w", err)
		}

		prvCfg.ReGroup = re

		re, err = regexp.Compile(cfg.RoleListRegex)
		if err != nil {
			return fmt.Errorf("invalid search group regex: %w", err)
		}

		prvCfg.ReRole = re

	} else {
		prvCfg.ReGroup = nil
		prvCfg.ReRole = nil
	}

	prvCfg.RoleAdminIDs = cfg.RoleAdminIDs
	prvCfg.RoleManagerIDs = cfg.RoleManagerIDs
	prvCfg.RoleAdvancedIDs = cfg.RoleAdvancedIDs
	prvCfg.RoleUserIDs = cfg.RoleUserIDs
	prvCfg.RoleDefault = cfg.RoleDefault

	prvCfg.SaveEmail = cfg.SaveEmail

	prvCfg.AllowInsecureTLS = cfg.AllowInsecureTLS
	if cfg.AllowInsecureTLS {
		l.log.Warn().Msg("LDAP: TLS certificate verification is DISABLED (allow_insecure_tls=true). Use only for testing or with trusted self-signed certificates.")
	}

	l.cfg.LoadCfg(prvCfg)

	return nil
}

func (l *LDAP) newConn() (*ldap.Conn, error) {
	cfg := l.cfg.Cfg()

	url := fmt.Sprintf("%s://%s:%d", cfg.Protocol, cfg.Host, cfg.Port)

	var opts []ldap.DialOpt
	if cfg.AllowInsecureTLS && cfg.Protocol == "ldaps" {
		opts = append(opts, ldap.DialWithTLSConfig(&tls.Config{
			InsecureSkipVerify: true,
		}))
	}

	conn, err := ldap.DialURL(url, opts...)
	if err != nil {
		return nil, fmt.Errorf("connect to the LDAP server: %w", err)
	}

	if err := conn.Bind(cfg.BindDN, cfg.Password); err != nil {
		return nil, fmt.Errorf("bind using the configuration user: %w", err)
	}

	return conn, nil
}

func (l *LDAP) listRoles(usr string) ([]string, error) {
	cfg := l.cfg.Cfg()

	conn, err := l.newConn()
	if err != nil {
		return nil, err
	}
	defer conn.Close()

	req := ldap.NewSearchRequest(
		cfg.RoleListSearchBase,
		ldap.ScopeWholeSubtree,
		ldap.NeverDerefAliases, 0, 0, false,
		fmt.Sprintf(cfg.RoleListFilter, ldap.EscapeFilter(usr)),
		[]string{cfg.RoleListField},
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
		roles = append(roles, entry.GetAttributeValues(cfg.RoleListField)...)
	}

	return roles, nil
}

func (l *LDAP) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	cfg := l.cfg.Cfg()

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

	attributes := []string{"dn", cfg.FieldUID, cfg.FieldUsername, cfg.FieldName, cfg.FieldEmail, cfg.FieldPhoto}
	if cfg.GuessCategory {
		attributes = append(attributes, cfg.FieldCategory)
	}
	if cfg.AutoRegister {
		attributes = append(attributes, cfg.FieldGroup)
	}

	req := ldap.NewSearchRequest(
		cfg.BaseSearch,
		ldap.ScopeWholeSubtree,
		ldap.NeverDerefAliases, 0, 0, false,
		fmt.Sprintf(cfg.Filter, ldap.EscapeFilter(usr)),
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

	username := matchRegex(cfg.ReUsername, entry.GetAttributeValue(cfg.FieldUsername))
	name := matchRegex(cfg.ReName, entry.GetAttributeValue(cfg.FieldName))
	email := matchRegex(cfg.ReEmail, entry.GetAttributeValue(cfg.FieldEmail))
	photo := matchRegex(cfg.RePhoto, entry.GetAttributeValue(cfg.FieldPhoto))

	u := &types.ProviderUserData{
		Provider: types.ProviderLDAP,
		Category: categoryID,
		UID:      matchRegex(cfg.ReUID, entry.GetAttributeValue(cfg.FieldUID)),

		Username: &username,
		Name:     &name,
		Email:    &email,
		Photo:    &photo,
	}

	if cfg.GuessCategory {
		attrCategories := entry.GetAttributeValues(cfg.FieldCategory)
		var attrGroups *[]string
		if cfg.AutoRegister {
			g := entry.GetAttributeValues(cfg.FieldGroup)
			attrGroups = &g
		}

		tkn, err := guessCategory(ctx, l.log, l.db, l.secret, cfg.ReCategory, attrCategories, attrGroups, nil, u)
		if err != nil {
			return nil, nil, nil, "", "", err
		}

		if tkn != "" {
			return nil, nil, nil, "", tkn, nil
		}
	}

	var g *model.Group
	secondary := []*model.Group{}
	if cfg.AutoRegister {
		//
		// Guess group
		//
		attrGroups := entry.GetAttributeValues(cfg.FieldGroup)
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
		if cfg.RoleListUseUserDN {
			searchID = entry.DN
		}

		attrRoles, lErr := l.listRoles(searchID)
		if lErr != nil {
			return nil, nil, nil, "", "", &ProviderError{
				User:   ErrInternal,
				Detail: fmt.Errorf("list all groups: %w", lErr),
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
	cfg := l.cfg.Cfg()

	if cfg.AutoRegister {
		if len(cfg.AutoRegisterRoles) != 0 {
			// If the user role is in the autoregister roles list, auto register
			return slices.Contains(cfg.AutoRegisterRoles, string(u.Role))
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
	return l.cfg.Cfg().SaveEmail
}

func (l *LDAP) GuessGroups(ctx context.Context, u *types.ProviderUserData, rawGroups []string) (*model.Group, []*model.Group, *ProviderError) {
	cfg := l.cfg.Cfg()

	return guessGroup(ctx, l.db, guessGroupOpts{
		Provider:     l,
		ReGroup:      cfg.ReGroup,
		DefaultGroup: cfg.GroupDefault,
	}, u, rawGroups)
}

func (l *LDAP) GuessRole(ctx context.Context, u *types.ProviderUserData, rawRoles []string) (*model.Role, *ProviderError) {
	cfg := l.cfg.Cfg()

	return guessRole(guessRoleOpts{
		ReRole:          cfg.ReRole,
		RoleAdminIDs:    cfg.RoleAdminIDs,
		RoleManagerIDs:  cfg.RoleManagerIDs,
		RoleAdvancedIDs: cfg.RoleAdvancedIDs,
		RoleUserIDs:     cfg.RoleUserIDs,
		RoleDefault:     cfg.RoleDefault,
	}, rawRoles)
}
