package provider

import (
	"context"
	"errors"
	"fmt"
	"log"
	"regexp"

	"github.com/go-ldap/ldap/v3"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
)

var _ Provider = &LDAP{}

type LDAP struct {
	cfg cfg.AuthenticationLDAP

	ReUID          *regexp.Regexp
	ReCategory     *regexp.Regexp
	ReGroup        *regexp.Regexp
	ReUsername     *regexp.Regexp
	ReName         *regexp.Regexp
	ReEmail        *regexp.Regexp
	RePhoto        *regexp.Regexp
	ReGroupsSearch *regexp.Regexp
}

func InitLDAP(cfg cfg.AuthenticationLDAP) *LDAP {
	l := &LDAP{cfg: cfg}

	re, err := regexp.Compile(cfg.RegexUID)
	if err != nil {
		log.Fatalf("invalid UID regex: %v", err)
	}
	l.ReUID = re

	re, err = regexp.Compile(cfg.RegexUsername)
	if err != nil {
		log.Fatalf("invalid username regex: %v", err)
	}
	l.ReUsername = re

	re, err = regexp.Compile(cfg.RegexName)
	if err != nil {
		log.Fatalf("invalid name regex: %v", err)
	}
	l.ReName = re

	re, err = regexp.Compile(cfg.RegexEmail)
	if err != nil {
		log.Fatalf("invalid email regex: %v", err)
	}
	l.ReEmail = re

	re, err = regexp.Compile(cfg.RegexPhoto)
	if err != nil {
		log.Fatalf("invalid photo regex: %v", err)
	}
	l.RePhoto = re

	if l.AutoRegister() {
		re, err = regexp.Compile(cfg.RegexCategory)
		if err != nil {
			log.Fatalf("invalid category regex: %v", err)
		}
		l.ReCategory = re

		re, err = regexp.Compile(cfg.RegexGroup)
		if err != nil {
			log.Fatalf("invalid group regex: %v", err)
		}
		l.ReGroup = re

		re, err = regexp.Compile(cfg.GroupsSearchRegex)
		if err != nil {
			log.Fatalf("invalid search group regex: %v", err)
		}
		l.ReGroupsSearch = re
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

func (l *LDAP) listAllGroups(usr string) ([]string, error) {
	conn, err := l.newConn()
	if err != nil {
		return nil, err
	}
	defer conn.Close()

	req := ldap.NewSearchRequest(
		l.cfg.GroupsSearch,
		ldap.ScopeWholeSubtree,
		ldap.NeverDerefAliases, 0, 0, false,
		fmt.Sprintf(l.cfg.GroupsFilter, ldap.EscapeFilter(usr)),
		[]string{l.cfg.GroupsSearchField},
		nil,
	)

	rsp, err := conn.Search(req)
	if err != nil {
		if ldap.IsErrorWithCode(err, ldap.LDAPResultNoSuchObject) {
			return nil, ErrInvalidCredentials
		}

		return nil, fmt.Errorf("get all the user groups: %w", err)
	}

	if len(rsp.Entries) == 0 {
		return nil, ErrInvalidCredentials
	}

	groups := []string{}
	for _, entry := range rsp.Entries {
		if g := matchRegex(l.ReGroupsSearch, entry.GetAttributeValue(l.cfg.GroupsSearchField)); g != "" {
			groups = append(groups, g)
		}
	}

	return groups, nil
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
	if l.AutoRegister() {
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

	usr_dn := entry.DN

	if err := conn.Bind(usr_dn, pwd); err != nil {
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

	var g *model.Group

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
		u.Category = matchRegex(l.ReCategory, entry.GetAttributeValue(l.cfg.FieldCategory))
	}

	if l.AutoRegister() {
		if !l.cfg.GuessCategory && u.Category != categoryID {
			return nil, nil, "", "", &ProviderError{
				User:   ErrInvalidCredentials,
				Detail: fmt.Errorf("category missmatch: expecting '%s', found '%s'", categoryID, u.Category),
			}
		}

		g = &model.Group{
			Category:      u.Category,
			ExternalAppID: fmt.Sprintf("provider-%s", l.String()),
			ExternalGID:   matchRegex(l.ReGroup, entry.GetAttributeValue(l.cfg.FieldGroup)),
			Description:   "This is a auto register created by the authentication service. This group maps a LDAP group",
		}

		// Ensure that we have found the group
		if g.ExternalGID == "" {
			// If there's no default group, throw an error
			if l.cfg.DefaultGroup == "" {
				return nil, nil, "", "", &ProviderError{
					User:   ErrInvalidCredentials,
					Detail: errors.New("empty user group"),
				}
			}

			// Otherwise set is as the ExternalGID
			g.ExternalGID = l.cfg.DefaultGroup
		}

		g.GenerateNameExternal(l.String())

		// List all the groups to setup the user role afterwards
		gSearchID := usr
		if l.cfg.GroupsSearchUseDN {
			gSearchID = entry.DN
		}

		allUsrGrps, err := l.listAllGroups(gSearchID)
		if err != nil {
			if !errors.Is(err, ErrInvalidCredentials) {
				return nil, nil, "", "", &ProviderError{
					User:   ErrInternal,
					Detail: fmt.Errorf("list all groups: %w", err),
				}
			}

			// If the error is ErrInvalidCredentials, means that the user is not part
			// of any group. If there's a default group configured, use it as allUsrGrps.
			// Otherwise, return the error
			if l.cfg.DefaultGroup == "" {
				return nil, nil, "", "", &ProviderError{
					User:   ErrInvalidCredentials,
					Detail: fmt.Errorf("list all groups: %w", err),
				}
			}

			allUsrGrps = []string{l.cfg.DefaultGroup}
		}

		// Get the role that has more privileges
		roles := []model.Role{model.RoleAdmin, model.RoleManager, model.RoleAdvanced, model.RoleUser}
		for i, groups := range [][]string{l.cfg.RoleAdminGroups, l.cfg.RoleManagerGroups, l.cfg.RoleAdvancedGroups, l.cfg.RoleUserGroups} {
			for _, g := range groups {
				for _, uGrp := range allUsrGrps {
					if uGrp == g {
						if roles[i].HasMorePrivileges(*u.Role) {
							u.Role = &roles[i]
						}
					}
				}
			}
		}

		// Role fallback
		if u.Role == nil {
			u.Role = &l.cfg.RoleDefault
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

func (l *LDAP) AutoRegister() bool {
	return l.cfg.AutoRegister
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
