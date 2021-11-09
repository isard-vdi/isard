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

	ReUID      *regexp.Regexp
	ReUsername *regexp.Regexp
	ReName     *regexp.Regexp
	ReEmail    *regexp.Regexp
	RePhoto    *regexp.Regexp
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

func (l *LDAP) Login(ctx context.Context, categoryID string, args map[string]string) (*model.User, string, error) {
	usr, pwd, err := parseLDAPArgs(args)
	if err != nil {
		return nil, "", err
	}

	conn, err := ldap.DialURL(fmt.Sprintf("%s://%s:%d", l.cfg.Protocol, l.cfg.Host, l.cfg.Port))
	if err != nil {
		return nil, "", fmt.Errorf("connect to the LDAP server: : %w", err)
	}

	if err := conn.Bind(l.cfg.BindDN, l.cfg.Password); err != nil {
		return nil, "", fmt.Errorf("bind using the configuration user: %w", err)
	}

	req := ldap.NewSearchRequest(
		l.cfg.BaseSearch,
		ldap.ScopeWholeSubtree,
		ldap.NeverDerefAliases, 0, 0, false,
		fmt.Sprintf(l.cfg.Filter, ldap.EscapeFilter(usr)),
		[]string{
			"dn",
			l.cfg.FieldUID,
			l.cfg.FieldUsername,
			l.cfg.FieldName,
			l.cfg.FieldEmail,
			l.cfg.FieldPhoto,
		},
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
		UID:      l.ReUID.FindString(entry.GetAttributeValue(l.cfg.FieldUID)),
		Provider: LDAPString,
		Category: categoryID,
		Username: l.ReUsername.FindString(entry.GetAttributeValue(l.cfg.FieldUsername)),
		Name:     l.ReName.FindString(entry.GetAttributeValue(l.cfg.FieldName)),
		Email:    l.ReEmail.FindString(entry.GetAttributeValue(l.cfg.FieldEmail)),
		Photo:    l.RePhoto.FindString(entry.GetAttributeValue(l.cfg.FieldPhoto)),
	}

	return u, "", nil
}

func (l *LDAP) Callback(context.Context, *CallbackClaims, map[string]string) (*model.User, string, error) {
	return nil, "", errInvalidIDP
}

func (l *LDAP) String() string {
	return LDAPString
}
