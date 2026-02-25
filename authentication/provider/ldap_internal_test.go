package provider

import (
	"context"
	"regexp"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"

	"github.com/stretchr/testify/assert"
)

func TestLDAPLoadConfig(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Input       model.LDAPConfig
		Expected    LDAPConfig
		ExpectedErr string
	}{
		"should load config with all fields and valid regexps": {
			Input: model.LDAPConfig{
				Protocol:   "ldaps",
				Host:       "ldap.example.com",
				Port:       636,
				BindDN:     "cn=admin,dc=example,dc=com",
				Password:   "secret",
				BaseSearch: "dc=example,dc=com",

				Filter:        "(uid=%s)",
				FieldUID:      "uid",
				RegexUID:      "^(.+)$",
				FieldUsername: "cn",
				RegexUsername: "^(.+)$",
				FieldName:     "displayName",
				RegexName:     "^(.+)$",
				FieldEmail:    "mail",
				RegexEmail:    "^(.+)$",
				FieldPhoto:    "jpegPhoto",
				RegexPhoto:    "^(.+)$",

				AutoRegister:      true,
				AutoRegisterRoles: []string{"admin", "user"},

				GuessCategory: true,
				FieldCategory: "ou",
				RegexCategory: "^(.+)$",

				FieldGroup:   "memberOf",
				RegexGroup:   "cn=([^,]+)",
				GroupDefault: "default-group",

				RoleListSearchBase: "ou=groups,dc=example,dc=com",
				RoleListFilter:     "(member=%s)",
				RoleListUseUserDN:  true,
				RoleListField:      "cn",
				RoleListRegex:      "^(.+)$",

				RoleAdminIDs:    []string{"admin-group"},
				RoleManagerIDs:  []string{"manager-group"},
				RoleAdvancedIDs: []string{"advanced-group"},
				RoleUserIDs:     []string{"user-group"},
				RoleDefault:     model.RoleUser,

				SaveEmail: true,
			},
			Expected: LDAPConfig{
				Protocol:   "ldaps",
				Host:       "ldap.example.com",
				Port:       636,
				BindDN:     "cn=admin,dc=example,dc=com",
				Password:   "secret",
				BaseSearch: "dc=example,dc=com",

				Filter:        "(uid=%s)",
				FieldUID:      "uid",
				ReUID:         regexp.MustCompile("^(.+)$"),
				FieldUsername: "cn",
				ReUsername:    regexp.MustCompile("^(.+)$"),
				FieldName:     "displayName",
				ReName:        regexp.MustCompile("^(.+)$"),
				FieldEmail:    "mail",
				ReEmail:       regexp.MustCompile("^(.+)$"),
				FieldPhoto:    "jpegPhoto",
				RePhoto:       regexp.MustCompile("^(.+)$"),

				AutoRegister:      true,
				AutoRegisterRoles: []string{"admin", "user"},

				GuessCategory: true,
				FieldCategory: "ou",
				ReCategory:    regexp.MustCompile("^(.+)$"),

				FieldGroup:   "memberOf",
				ReGroup:      regexp.MustCompile("cn=([^,]+)"),
				GroupDefault: "default-group",

				RoleListSearchBase: "ou=groups,dc=example,dc=com",
				RoleListFilter:     "(member=%s)",
				RoleListUseUserDN:  true,
				RoleListField:      "cn",
				ReRole:             regexp.MustCompile("^(.+)$"),

				RoleAdminIDs:    []string{"admin-group"},
				RoleManagerIDs:  []string{"manager-group"},
				RoleAdvancedIDs: []string{"advanced-group"},
				RoleUserIDs:     []string{"user-group"},
				RoleDefault:     model.RoleUser,

				SaveEmail: true,
			},
		},
		"should return error for invalid UID regex": {
			Input:       model.LDAPConfig{RegexUID: "[invalid"},
			ExpectedErr: "invalid UID regex",
		},
		"should return error for invalid username regex": {
			Input: model.LDAPConfig{
				RegexUID:      ".*",
				RegexUsername: "[invalid",
			},
			ExpectedErr: "invalid username regex",
		},
		"should return error for invalid name regex": {
			Input: model.LDAPConfig{
				RegexUID:      ".*",
				RegexUsername: ".*",
				RegexName:     "[invalid",
			},
			ExpectedErr: "invalid name regex",
		},
		"should return error for invalid email regex": {
			Input: model.LDAPConfig{
				RegexUID:      ".*",
				RegexUsername: ".*",
				RegexName:     ".*",
				RegexEmail:    "[invalid",
			},
			ExpectedErr: "invalid email regex",
		},
		"should return error for invalid photo regex": {
			Input: model.LDAPConfig{
				RegexUID:      ".*",
				RegexUsername: ".*",
				RegexName:     ".*",
				RegexEmail:    ".*",
				RegexPhoto:    "[invalid",
			},
			ExpectedErr: "invalid photo regex",
		},
		"should return error for invalid category regex": {
			Input: model.LDAPConfig{
				RegexUID:      ".*",
				RegexUsername: ".*",
				RegexName:     ".*",
				RegexEmail:    ".*",
				RegexPhoto:    ".*",
				GuessCategory: true,
				RegexCategory: "[invalid",
			},
			ExpectedErr: "invalid category regex",
		},
		"should return error for invalid group regex": {
			Input: model.LDAPConfig{
				RegexUID:      ".*",
				RegexUsername: ".*",
				RegexName:     ".*",
				RegexEmail:    ".*",
				RegexPhoto:    ".*",
				AutoRegister:  true,
				RegexGroup:    "[invalid",
			},
			ExpectedErr: "invalid group regex",
		},
		"should return error for invalid role list regex": {
			Input: model.LDAPConfig{
				RegexUID:      ".*",
				RegexUsername: ".*",
				RegexName:     ".*",
				RegexEmail:    ".*",
				RegexPhoto:    ".*",
				AutoRegister:  true,
				RegexGroup:    ".*",
				RoleListRegex: "[invalid",
			},
			ExpectedErr: "invalid search group regex",
		},
		"should set ReCategory to nil when GuessCategory is false": {
			Input: model.LDAPConfig{
				RegexUID:      ".*",
				RegexUsername: ".*",
				RegexName:     ".*",
				RegexEmail:    ".*",
				RegexPhoto:    ".*",
			},
			Expected: LDAPConfig{
				ReUID:      regexp.MustCompile(".*"),
				ReUsername: regexp.MustCompile(".*"),
				ReName:     regexp.MustCompile(".*"),
				ReEmail:    regexp.MustCompile(".*"),
				RePhoto:    regexp.MustCompile(".*"),
			},
		},
		"should compile ReCategory when GuessCategory is true": {
			Input: model.LDAPConfig{
				RegexUID:      ".*",
				RegexUsername: ".*",
				RegexName:     ".*",
				RegexEmail:    ".*",
				RegexPhoto:    ".*",
				GuessCategory: true,
				RegexCategory: "(.*)",
			},
			Expected: LDAPConfig{
				ReUID:         regexp.MustCompile(".*"),
				ReUsername:    regexp.MustCompile(".*"),
				ReName:        regexp.MustCompile(".*"),
				ReEmail:       regexp.MustCompile(".*"),
				RePhoto:       regexp.MustCompile(".*"),
				GuessCategory: true,
				ReCategory:    regexp.MustCompile("(.*)"),
			},
		},
		"should set ReGroup and ReRole to nil when AutoRegister is false": {
			Input: model.LDAPConfig{
				RegexUID:      ".*",
				RegexUsername: ".*",
				RegexName:     ".*",
				RegexEmail:    ".*",
				RegexPhoto:    ".*",
			},
			Expected: LDAPConfig{
				ReUID:      regexp.MustCompile(".*"),
				ReUsername: regexp.MustCompile(".*"),
				ReName:     regexp.MustCompile(".*"),
				ReEmail:    regexp.MustCompile(".*"),
				RePhoto:    regexp.MustCompile(".*"),
			},
		},
		"should compile ReGroup and ReRole when AutoRegister is true": {
			Input: model.LDAPConfig{
				RegexUID:      ".*",
				RegexUsername: ".*",
				RegexName:     ".*",
				RegexEmail:    ".*",
				RegexPhoto:    ".*",
				AutoRegister:  true,
				RegexGroup:    "(.*)",
				RoleListRegex: "(.*)",
			},
			Expected: LDAPConfig{
				ReUID:        regexp.MustCompile(".*"),
				ReUsername:   regexp.MustCompile(".*"),
				ReName:       regexp.MustCompile(".*"),
				ReEmail:      regexp.MustCompile(".*"),
				RePhoto:      regexp.MustCompile(".*"),
				AutoRegister: true,
				ReGroup:      regexp.MustCompile("(.*)"),
				ReRole:       regexp.MustCompile("(.*)"),
			},
		},
	}

	assertRegexp := func(expected, actual *regexp.Regexp) {
		if expected == nil {
			assert.Nil(actual)
		} else if assert.NotNil(actual) {
			assert.Equal(expected.String(), actual.String())
		}
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			l := &LDAP{
				cfg: &cfgManager[LDAPConfig]{cfg: &LDAPConfig{}},
			}

			err := l.LoadConfig(context.Background(), tc.Input)

			if tc.ExpectedErr != "" {
				assert.ErrorContains(err, tc.ExpectedErr)
				return
			}

			assert.NoError(err)

			cfg := l.cfg.Cfg()

			// Simple fields
			assert.Equal(tc.Expected.Protocol, cfg.Protocol)
			assert.Equal(tc.Expected.Host, cfg.Host)
			assert.Equal(tc.Expected.Port, cfg.Port)
			assert.Equal(tc.Expected.BindDN, cfg.BindDN)
			assert.Equal(tc.Expected.Password, cfg.Password)
			assert.Equal(tc.Expected.BaseSearch, cfg.BaseSearch)

			// Field mappings
			assert.Equal(tc.Expected.Filter, cfg.Filter)
			assert.Equal(tc.Expected.FieldUID, cfg.FieldUID)
			assert.Equal(tc.Expected.FieldUsername, cfg.FieldUsername)
			assert.Equal(tc.Expected.FieldName, cfg.FieldName)
			assert.Equal(tc.Expected.FieldEmail, cfg.FieldEmail)
			assert.Equal(tc.Expected.FieldPhoto, cfg.FieldPhoto)

			// Compiled regexps
			assertRegexp(tc.Expected.ReUID, cfg.ReUID)
			assertRegexp(tc.Expected.ReUsername, cfg.ReUsername)
			assertRegexp(tc.Expected.ReName, cfg.ReName)
			assertRegexp(tc.Expected.ReEmail, cfg.ReEmail)
			assertRegexp(tc.Expected.RePhoto, cfg.RePhoto)
			assertRegexp(tc.Expected.ReCategory, cfg.ReCategory)
			assertRegexp(tc.Expected.ReGroup, cfg.ReGroup)
			assertRegexp(tc.Expected.ReRole, cfg.ReRole)

			// Auto register
			assert.Equal(tc.Expected.AutoRegister, cfg.AutoRegister)
			assert.Equal(tc.Expected.AutoRegisterRoles, cfg.AutoRegisterRoles)

			// Category guessing
			assert.Equal(tc.Expected.GuessCategory, cfg.GuessCategory)
			assert.Equal(tc.Expected.FieldCategory, cfg.FieldCategory)

			// Group
			assert.Equal(tc.Expected.FieldGroup, cfg.FieldGroup)
			assert.Equal(tc.Expected.GroupDefault, cfg.GroupDefault)

			// Role list
			assert.Equal(tc.Expected.RoleListSearchBase, cfg.RoleListSearchBase)
			assert.Equal(tc.Expected.RoleListFilter, cfg.RoleListFilter)
			assert.Equal(tc.Expected.RoleListUseUserDN, cfg.RoleListUseUserDN)
			assert.Equal(tc.Expected.RoleListField, cfg.RoleListField)

			// Role IDs
			assert.Equal(tc.Expected.RoleAdminIDs, cfg.RoleAdminIDs)
			assert.Equal(tc.Expected.RoleManagerIDs, cfg.RoleManagerIDs)
			assert.Equal(tc.Expected.RoleAdvancedIDs, cfg.RoleAdvancedIDs)
			assert.Equal(tc.Expected.RoleUserIDs, cfg.RoleUserIDs)
			assert.Equal(tc.Expected.RoleDefault, cfg.RoleDefault)

			// Save email
			assert.Equal(tc.Expected.SaveEmail, cfg.SaveEmail)
		})
	}
}

func TestLDAPAutoRegister(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Cfg      LDAPConfig
		User     *model.User
		Expected bool
	}{
		"should return true when auto register is enabled and no role restrictions": {
			Cfg: LDAPConfig{
				AutoRegister: true,
			},
			User:     &model.User{Role: model.RoleUser},
			Expected: true,
		},
		"should return false when auto register is disabled": {
			Cfg: LDAPConfig{
				AutoRegister: false,
			},
			User:     &model.User{Role: model.RoleUser},
			Expected: false,
		},
		"should return true when user role is in the allowed roles list": {
			Cfg: LDAPConfig{
				AutoRegister:      true,
				AutoRegisterRoles: []string{"admin", "user"},
			},
			User:     &model.User{Role: model.RoleUser},
			Expected: true,
		},
		"should return false when user role is not in the allowed roles list": {
			Cfg: LDAPConfig{
				AutoRegister:      true,
				AutoRegisterRoles: []string{"admin"},
			},
			User:     &model.User{Role: model.RoleUser},
			Expected: false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			l := &LDAP{
				cfg: &cfgManager[LDAPConfig]{cfg: &tc.Cfg},
			}

			assert.Equal(tc.Expected, l.AutoRegister(tc.User))
		})
	}
}

func TestLDAPString(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Expected string
	}{
		"should return the LDAP provider type": {
			Expected: types.ProviderLDAP,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			l := &LDAP{}

			assert.Equal(tc.Expected, l.String())
		})
	}
}

func TestLDAPSaveEmail(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Cfg      LDAPConfig
		Expected bool
	}{
		"should return true when SaveEmail is enabled": {
			Cfg:      LDAPConfig{SaveEmail: true},
			Expected: true,
		},
		"should return false when SaveEmail is disabled": {
			Cfg:      LDAPConfig{SaveEmail: false},
			Expected: false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			l := &LDAP{
				cfg: &cfgManager[LDAPConfig]{cfg: &tc.Cfg},
			}

			assert.Equal(tc.Expected, l.SaveEmail())
		})
	}
}

func TestLDAPGuessRole(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Cfg          LDAPConfig
		RawRoles     []string
		ExpectedRole model.Role
		ExpectedErr  string
	}{
		"should delegate to guessRole and return the correct role": {
			Cfg: func() LDAPConfig {
				l := &LDAP{
					cfg: &cfgManager[LDAPConfig]{cfg: &LDAPConfig{}},
				}
				_ = l.LoadConfig(context.Background(), model.LDAPConfig{
					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",
					AutoRegister:  true,
					RegexGroup:    ".*",
					RoleListRegex: ".*",
					RoleAdminIDs:  []string{"admin"},
					RoleDefault:   model.RoleUser,
				})
				return l.cfg.Cfg()
			}(),
			RawRoles:     []string{"admin"},
			ExpectedRole: model.RoleAdmin,
		},
		"should fallback to default role when no match": {
			Cfg: func() LDAPConfig {
				l := &LDAP{
					cfg: &cfgManager[LDAPConfig]{cfg: &LDAPConfig{}},
				}
				_ = l.LoadConfig(context.Background(), model.LDAPConfig{
					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",
					AutoRegister:  true,
					RegexGroup:    ".*",
					RoleListRegex: ".*",
					RoleDefault:   model.RoleUser,
				})
				return l.cfg.Cfg()
			}(),
			RawRoles:     []string{"unknown-role"},
			ExpectedRole: model.RoleUser,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			l := &LDAP{
				cfg: &cfgManager[LDAPConfig]{cfg: &tc.Cfg},
			}

			role, err := l.GuessRole(context.Background(), nil, tc.RawRoles)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.Nil(err)
				assert.Equal(tc.ExpectedRole, *role)
			}
		})
	}
}
