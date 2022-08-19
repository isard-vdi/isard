package provider

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"regexp"

	"github.com/go-ldap/ldap/v3"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
)

const LDAPString = "ldap"

type LDAP struct {
	cfg cfg.AuthenticationLDAP

	ReUID          *regexp.Regexp
	ReCategory     *regexp.Regexp
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

		re, err = regexp.Compile(cfg.GroupsSearchRegex)
		if err != nil {
			log.Fatalf("invalid search group regex: %v", err)
		}
		l.ReGroupsSearch = re
	}

	return l
}

type ldapArgs struct {
	Username string `json:"username,omitempty"`
	Password string `json:"password,omitempty"`
}

func parseLDAPArgs(args map[string]string) (string, string, error) {
	username := args["username"]
	password := args["password"]

	creds := &ldapArgs{}
	if body, ok := args[RequestBodyArgsKey]; ok && body != "" {
		if err := json.Unmarshal([]byte(body), creds); err != nil {
			return "", "", fmt.Errorf("unmarshal LDAP authentication request body: %w", err)
		}
	}

	if username == "" {
		if creds.Username == "" {
			return "", "", errors.New("username not provided")
		}

		username = creds.Username
	}

	if password == "" {
		if creds.Password == "" {
			return "", "", errors.New("password not provided")
		}

		password = creds.Password
	}

	return username, password, nil
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

func (l *LDAP) Login(ctx context.Context, categoryID string, args map[string]string) (*model.User, string, error) {
	usr, pwd, err := parseLDAPArgs(args)
	if err != nil {
		return nil, "", err
	}

	conn, err := l.newConn()
	if err != nil {
		return nil, "", err
	}
	defer conn.Close()

	attributes := []string{"dn", l.cfg.FieldUID, l.cfg.FieldUsername, l.cfg.FieldName, l.cfg.FieldEmail, l.cfg.FieldPhoto}
	if l.cfg.GuessCategory {
		attributes = append(attributes, l.cfg.FieldCategory)
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
			return nil, "", ErrInvalidCredentials
		}

		return nil, "", fmt.Errorf("serach the user: %w", err)
	}

	if len(rsp.Entries) != 1 {
		return nil, "", ErrInvalidCredentials
	}

	entry := rsp.Entries[0]

	usr_dn := entry.DN

	if err := conn.Bind(usr_dn, pwd); err != nil {
		if ldap.IsErrorWithCode(err, ldap.LDAPResultInvalidCredentials) {
			return nil, "", ErrInvalidCredentials
		}

		return nil, "", fmt.Errorf("bind the user: %w", err)
	}

	u := &model.User{
		UID:      matchRegex(l.ReUID, entry.GetAttributeValue(l.cfg.FieldUID)),
		Provider: LDAPString,
		Category: categoryID,
		Username: matchRegex(l.ReUsername, entry.GetAttributeValue(l.cfg.FieldUsername)),
		Name:     matchRegex(l.ReName, entry.GetAttributeValue(l.cfg.FieldName)),
		Email:    matchRegex(l.ReEmail, entry.GetAttributeValue(l.cfg.FieldEmail)),
		Photo:    matchRegex(l.RePhoto, entry.GetAttributeValue(l.cfg.FieldPhoto)),
	}

	if l.cfg.GuessCategory {
		u.Category = matchRegex(l.ReCategory, entry.GetAttributeValue(l.cfg.FieldCategory))
	}

	if l.AutoRegister() {
		if !l.cfg.GuessCategory && u.Category != categoryID {
			return nil, "", ErrInvalidCredentials
		}

		gSearchID := usr
		if l.cfg.GroupsSearchUseDN {
			gSearchID = entry.DN
		}

		allUsrGrps, err := l.listAllGroups(gSearchID)
		if err != nil {
			return nil, "", err
		}

		grp := &model.Group{Category: u.Category}

		roles := []model.Role{model.RoleAdmin, model.RoleManager, model.RoleAdvanced, model.RoleUser}
		for i, groups := range [][]string{l.cfg.RoleAdminGroups, l.cfg.RoleManagerGroups, l.cfg.RoleAdvancedGroups, l.cfg.RoleUserGroups} {
			for _, g := range groups {
				for _, uGrp := range allUsrGrps {
					if uGrp == g {
						if roles[i].HasMorePrivileges(u.Role) {
							grp.Name = g
							u.Role = roles[i]
						}
					}
				}
			}
		}
		if u.Role == "" {
			grp.Name = allUsrGrps[0]
			u.Role = l.cfg.RoleDefault
		}

		u.Group = grp.JoinID()
	}

	return u, "", nil
}

func (l *LDAP) Callback(context.Context, *CallbackClaims, map[string]string) (*model.User, string, error) {
	return nil, "", errInvalidIDP
}

func (l *LDAP) AutoRegister() bool {
	return l.cfg.AutoRegister
}

func (l *LDAP) String() string {
	return LDAPString
}
