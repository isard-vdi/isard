package provider

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"slices"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"

	"github.com/go-ldap/ldap/v3"
	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var _ Provider = &LDAP{}

type LDAP struct {
	cfg    cfg.AuthenticationLDAP
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
}

func InitLDAP(cfg cfg.AuthenticationLDAP, secret string, log *zerolog.Logger, db r.QueryExecutor) *LDAP {
	l := &LDAP{
		cfg:    cfg,
		secret: secret,
		log:    log,
		db:     db,
	}

	re, err := regexp.Compile(cfg.RegexUID)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid UID regex")
	}
	l.ReUID = re

	re, err = regexp.Compile(cfg.RegexUsername)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid username regex")
	}
	l.ReUsername = re

	re, err = regexp.Compile(cfg.RegexName)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid name regex")
	}
	l.ReName = re

	re, err = regexp.Compile(cfg.RegexEmail)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid email regex")
	}
	l.ReEmail = re

	re, err = regexp.Compile(cfg.RegexPhoto)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid photo regex")
	}
	l.RePhoto = re

	if l.cfg.GuessCategory {
		re, err = regexp.Compile(cfg.RegexCategory)
		if err != nil {
			log.Fatal().Err(err).Msg("invalid category regex")
		}
		l.ReCategory = re
	}

	if l.cfg.AutoRegister {
		re, err = regexp.Compile(cfg.RegexGroup)
		if err != nil {
			log.Fatal().Err(err).Msg("invalid group regex")
		}
		l.ReGroup = re

		re, err = regexp.Compile(cfg.RoleListRegex)
		if err != nil {
			log.Fatal().Err(err).Msg("invalid search group regex")
		}
		l.ReRole = re
	}

	return l
}

func (l *LDAP) newConn() (*ldap.Conn, error) {
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

func (l *LDAP) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	usr := *args.FormUsername
	pwd := *args.FormPassword

	conn, err := l.newConn()
	if err != nil {
		return nil, nil, "", "", &ProviderError{
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
			return nil, nil, "", "", &ProviderError{
				User:   ErrInvalidCredentials,
				Detail: errors.New("user not found"),
			}
		}

		return nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("serach the user: %w", err),
		}
	}

	if len(rsp.Entries) != 1 {
		return nil, nil, "", "", &ProviderError{
			User:   ErrInvalidCredentials,
			Detail: fmt.Errorf("user not found: found '%d' users", len(rsp.Entries)),
		}
	}

	entry := rsp.Entries[0]

	usrDN := entry.DN

	if err := conn.Bind(usrDN, pwd); err != nil {
		if ldap.IsErrorWithCode(err, ldap.LDAPResultInvalidCredentials) {
			return nil, nil, "", "", &ProviderError{
				User:   ErrInvalidCredentials,
				Detail: errors.New("invalid password"),
			}
		}

		return nil, nil, "", "", &ProviderError{
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
		tkn, err := guessCategory(ctx, l.log, l.db, l.secret, l.ReCategory, attrCategories, u)
		if err != nil {
			return nil, nil, "", "", err
		}

		if tkn != "" {
			return nil, nil, "", tkn, nil
		}
	}

	var g *model.Group
	if l.cfg.AutoRegister {
		//
		// Guess group
		//
		attrGroups := entry.GetAttributeValues(l.cfg.FieldGroup)
		if len(attrGroups) == 0 {
			l.log.Debug().Msg("missing groups attribute, will fallback to the default if defined")
		}

		var err *ProviderError
		g, err = guessGroup(guessGroupOpts{
			Provider:     l,
			ReGroup:      l.ReGroup,
			DefaultGroup: l.cfg.GroupDefault,
		}, u, attrGroups)
		if err != nil {
			return nil, nil, "", "", err
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
			return nil, nil, "", "", &ProviderError{
				User:   ErrInternal,
				Detail: fmt.Errorf("list all groups: %w", err),
			}
		}

		u.Role, err = guessRole(guessRoleOpts{
			ReRole:          l.ReRole,
			RoleAdminIDs:    l.cfg.RoleAdminIDs,
			RoleManagerIDs:  l.cfg.RoleManagerIDs,
			RoleAdvancedIDs: l.cfg.RoleAdvancedIDs,
			RoleUserIDs:     l.cfg.RoleUserIDs,
			RoleDefault:     l.cfg.RoleDefault,
		}, attrRoles)
		if err != nil {
			return nil, nil, "", "", err
		}
	}

	return g, u, "", "", nil
}

func (l *LDAP) Callback(context.Context, *token.CallbackClaims, CallbackArgs) (*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	return nil, nil, "", "", &ProviderError{
		User:   errInvalidIDP,
		Detail: errors.New("the LDAP provider doesn't support the callback operation"),
	}
}

func (l *LDAP) AutoRegister(u *model.User) bool {
	if l.cfg.AutoRegister {
		if len(l.cfg.AutoRegisterRoles) != 0 {
			// If the user role is in the autoregister roles list, auto register
			return slices.Contains(l.cfg.AutoRegisterRoles, string(u.Role))
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
