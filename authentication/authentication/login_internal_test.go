package authentication

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/providermanager"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"gitlab.com/isard/isardvdi/pkg/sdk"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestStartLogin(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB       func(*r.Mock)
		PrepareAPI      func(*sdk.MockSdk)
		PrepareProvider func(*provider.MockProvider)

		RemoteAddr       string
		Provider         string
		CategoryID       string
		Group            *model.Group
		SecondaryGroups  []*model.Group
		ProviderUserData func() *types.ProviderUserData
		Redirect         string

		CheckToken       func(string)
		ExpectedRedirect string
		ExpectedErr      string
	}{
		"should sign a register token if the user is missing and the provider doesn't support autoregistration": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				))).Return([]interface{}{}, nil)

				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"local": map[string]interface{}{
								"email_domain_restriction": map[string]interface{}{"enabled": true, "allowed": []string{"example.org"}},
							},
						},
					},
				}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(false)
			},

			Provider:   "local",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseRegisterToken("", ss)
				require.NoError(err)

				assert.Equal("local", tkn.Provider)
				assert.Equal("08fff46e-cbd3-40d2-9d8e-e2de7a8da654", tkn.UserID)
				assert.Equal("nefix", tkn.Username)
				assert.Equal("default", tkn.CategoryID)
				assert.Equal("Néfix Estrada", tkn.Name)
				assert.Equal("nefix@example.org", tkn.Email)
				assert.Equal("", tkn.Photo)
			},
			ExpectedRedirect: "/",
		},
		"should autoregister both the groups and user correctly": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654"),
					r.Eq(r.Row.Field("provider"), "mock"),
					r.Eq(r.Row.Field("category"), "default"),
				))).Return([]interface{}{}, nil)

				m.On(r.Table("groups").Filter(r.And(
					r.Eq(r.Row.Field("parent_category"), "default"),
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "my group ID"),
				))).Return([]interface{}{}, nil)

				m.On(r.Table("groups").Filter(r.And(
					r.Eq(r.Row.Field("parent_category"), "default"),
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "existing secondary group"),
				))).Return([]interface{}{
					map[string]interface{}{
						"id": "imagine an UUID here",
					},
				}, nil)

				m.On(r.Table("groups").Filter(r.And(
					r.Eq(r.Row.Field("parent_category"), "default"),
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "other secondary group"),
				))).Return([]interface{}{}, nil)

				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"local": map[string]interface{}{
								"email_domain_restriction": map[string]interface{}{"enabled": true, "allowed": []string{"example.org"}},
							},
						},
					},
				}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {
				genID := "uuid here!"
				c.On("AdminGroupCreate", mock.AnythingOfType("context.backgroundCtx"), "default", "category", "category", "some description", "provider-saml", "my group ID").Return(&sdk.Group{
					ID:  &genID,
					UID: &genID,
				}, nil)
				c.On("AdminGroupCreate", mock.AnythingOfType("context.backgroundCtx"), "default", "category", "category", "some description", "provider-saml", "other secondary group").Return(&sdk.Group{
					ID:  &genID,
					UID: &genID,
				}, nil)
				c.On("AdminUserAutoRegister", mock.AnythingOfType("context.backgroundCtx"), mock.AnythingOfType("string"), "advanced", "uuid here!", []string{"imagine an UUID here", "uuid here!"}).Return("user ID", nil)
				c.On("AdminUserRequiredDisclaimerAcknowledgement", mock.AnythingOfType("context.backgroundCtx"), "user ID").Return(false, nil)
				c.On("AdminUserRequiredEmailVerification", mock.AnythingOfType("context.backgroundCtx"), "user ID").Return(false, nil)
				c.On("AdminUserRequiredPasswordReset", mock.AnythingOfType("context.backgroundCtx"), "user ID").Return(true, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)
			},
			Provider:   "mock",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "my group ID",
				Name:          "category",
				Description:   "some description",
			},
			SecondaryGroups: []*model.Group{{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "existing secondary group",
				Name:          "category",
				Description:   "some description",
			}, {
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "other secondary group",
				Name:          "category",
				Description:   "some description",
			}},
			ProviderUserData: func() *types.ProviderUserData {
				role := model.RoleAdvanced
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				return &types.ProviderUserData{
					Provider: "mock",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Role:     &role,
					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParsePasswordResetRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user ID", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should return an error if there is an error getting the category": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return(nil, fmt.Errorf("Category error"))
			},
			PrepareAPI: func(c *sdk.MockSdk) {},

			Provider:   "local",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "pau"
				name := "Pau Abril"
				email := "🐐@💌.kz"

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "905d7714-df00-499a-8b0a-7d7a0a40191f",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			ExpectedErr: "get category: Category error",
		},
		"should work as expected if the user doesn't have an email, but there's no allowed domains configured": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), uuid.Max.String()),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				))).Return([]interface{}{}, nil)

				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"local": map[string]interface{}{
								"email_domain_restriction": map[string]interface{}{"enabled": false},
							},
						},
					},
				}, nil)
			},
			PrepareAPI: func(s *sdk.MockSdk) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(false)
			},

			Provider:   "local",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      uuid.Max.String(),

					Username: &username,
					Name:     &name,
				}
			},

			CheckToken: func(ss string) {
				tkn, err := token.ParseRegisterToken("", ss)

				require.NoError(err)

				assert.Equal("local", tkn.Provider)
				assert.Equal(uuid.Max.String(), tkn.UserID)
				assert.Equal("nefix", tkn.Username)
				assert.Equal("default", tkn.CategoryID)
				assert.Equal("Néfix Estrada", tkn.Name)
				assert.Equal("", tkn.Email)
				assert.Equal("", tkn.Photo)
			},
		},
		"should return ErrUserDisallowed when provider is disabled in category": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"local": map[string]interface{}{
								"disabled":                 true,
								"email_domain_restriction": map[string]interface{}{"enabled": false},
							},
						},
					},
				}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},

			Provider:   "local",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			ExpectedErr: provider.ErrUserDisallowed.Error(),
		},
		"should return ErrUserDisallowed when email domain is not in allowed domains": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"local": map[string]interface{}{
								"email_domain_restriction": map[string]interface{}{"enabled": true, "allowed": []string{"example.org"}},
							},
						},
					},
				}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},

			Provider:   "local",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@bad.com"

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			ExpectedErr: provider.ErrUserDisallowed.Error(),
		},
		"should return ErrUserDisallowed when user has no email but allowed domains are set": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"local": map[string]interface{}{
								"email_domain_restriction": map[string]interface{}{"enabled": true, "allowed": []string{"example.org"}},
							},
						},
					},
				}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},

			Provider:   "local",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Username: &username,
					Name:     &name,
				}
			},
			Redirect: "/",

			ExpectedErr: provider.ErrUserDisallowed.Error(),
		},
		"should allow default admin even when provider is disabled": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"local": map[string]interface{}{
								"disabled":                 true,
								"email_domain_restriction": map[string]interface{}{"enabled": false},
							},
						},
					},
				}, nil)

				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "admin"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				))).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(false)
			},

			Provider:   "local",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "admin"
				name := "Administrator"
				email := "admin@example.org"

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "admin",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseRegisterToken("", ss)
				require.NoError(err)

				assert.Equal("local", tkn.Provider)
				assert.Equal("admin", tkn.UserID)
				assert.Equal("admin", tkn.Username)
				assert.Equal("default", tkn.CategoryID)
			},
			ExpectedRedirect: "/",
		},
		"should allow default admin even when domain is not allowed": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"local": map[string]interface{}{
								"email_domain_restriction": map[string]interface{}{"enabled": true, "allowed": []string{"example.org"}},
							},
						},
					},
				}, nil)

				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "admin"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				))).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(false)
			},

			Provider:   "local",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "admin"
				name := "Administrator"
				email := "admin@wrong.com"

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "admin",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseRegisterToken("", ss)
				require.NoError(err)

				assert.Equal("local", tkn.Provider)
				assert.Equal("admin", tkn.UserID)
				assert.Equal("admin", tkn.Username)
				assert.Equal("default", tkn.CategoryID)
			},
			ExpectedRedirect: "/",
		},
		"should work when category has no authentication config": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				))).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(false)
			},

			Provider:   "local",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseRegisterToken("", ss)
				require.NoError(err)

				assert.Equal("local", tkn.Provider)
				assert.Equal("08fff46e-cbd3-40d2-9d8e-e2de7a8da654", tkn.UserID)
				assert.Equal("nefix", tkn.Username)
				assert.Equal("default", tkn.CategoryID)
			},
			ExpectedRedirect: "/",
		},
		"should work when category has authentication but provider is not configured": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"google": map[string]interface{}{
								"email_domain_restriction": map[string]interface{}{"enabled": true, "allowed": []string{"google.com"}},
							},
						},
					},
				}, nil)

				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654"),
					r.Eq(r.Row.Field("provider"), "ldap"),
					r.Eq(r.Row.Field("category"), "default"),
				))).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(false)
			},

			Provider:   "ldap",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				return &types.ProviderUserData{
					Provider: "ldap",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseRegisterToken("", ss)
				require.NoError(err)

				assert.Equal("ldap", tkn.Provider)
				assert.Equal("08fff46e-cbd3-40d2-9d8e-e2de7a8da654", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should work when provider is enabled in category with matching domain": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"local": map[string]interface{}{
								"email_domain_restriction": map[string]interface{}{"enabled": true, "allowed": []string{"example.org"}},
							},
						},
					},
				}, nil)

				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				))).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(false)
			},

			Provider:   "local",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseRegisterToken("", ss)
				require.NoError(err)

				assert.Equal("local", tkn.Provider)
				assert.Equal("08fff46e-cbd3-40d2-9d8e-e2de7a8da654", tkn.UserID)
				assert.Equal("nefix", tkn.Username)
				assert.Equal("default", tkn.CategoryID)
				assert.Equal("nefix@example.org", tkn.Email)
			},
			ExpectedRedirect: "/",
		},
		"should check SAML provider category config correctly": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"saml": map[string]interface{}{
								"disabled":                 true,
								"email_domain_restriction": map[string]interface{}{"enabled": false},
							},
						},
					},
				}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			ExpectedErr: provider.ErrUserDisallowed.Error(),
		},
		"should check Google provider category config correctly": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"google": map[string]interface{}{
								"disabled":                 true,
								"email_domain_restriction": map[string]interface{}{"enabled": false},
							},
						},
					},
				}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},

			Provider:   "google",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				return &types.ProviderUserData{
					Provider: "google",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			ExpectedErr: provider.ErrUserDisallowed.Error(),
		},
		"should check LDAP provider category config correctly": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"ldap": map[string]interface{}{
								"disabled":                 true,
								"email_domain_restriction": map[string]interface{}{"enabled": false},
							},
						},
					},
				}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},

			Provider:   "ldap",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				return &types.ProviderUserData{
					Provider: "ldap",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			ExpectedErr: provider.ErrUserDisallowed.Error(),
		},
		"should return error when email address is malformed": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id": "default",
						"authentication": map[string]interface{}{
							"local": map[string]interface{}{
								"email_domain_restriction": map[string]interface{}{"enabled": true, "allowed": []string{"example.org"}},
							},
						},
					},
				}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},

			Provider:   "local",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "invalid-email"

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			ExpectedErr: "parse user email address: 'invalid-email': mail: missing '@' or angle-addr",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()

			log := log.New("authentication-test", "debug")

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			apiMock := sdk.NewMockSdk(t)
			if tc.PrepareAPI != nil {
				tc.PrepareAPI(apiMock)
			}

			providerMock := provider.NewMockProvider(t)
			if tc.PrepareProvider != nil {
				tc.PrepareProvider(providerMock)
			}

			prvManagerMock := providermanager.NewMockProvidermanager(t)
			prvManagerMock.On("Provider", tc.Provider, tc.CategoryID).Return(providerMock)

			a := &Authentication{
				Log:        log,
				Secret:     "",
				BaseURL:    &url.URL{Scheme: "https", Host: "localhost"},
				DB:         dbMock,
				API:        apiMock,
				prvManager: prvManagerMock,
			}

			p := a.Provider(tc.Provider, tc.CategoryID)

			tkn, redirect, err := a.startLogin(ctx, tc.RemoteAddr, p, tc.Group, tc.SecondaryGroups, tc.ProviderUserData(), tc.Redirect)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken == nil {
				assert.Empty(tkn)
			} else {
				tc.CheckToken(tkn)
			}
			assert.Equal(tc.ExpectedRedirect, redirect)

			dbMock.AssertExpectations(t)
			apiMock.AssertExpectations(t)
		})
	}
}

func TestFinishCategorySelect(t *testing.T) {
	require := require.New(t)

	cases := map[string]struct {
		PrepareDB              func(*r.Mock)
		PrepareAPI             func(*sdk.MockSdk)
		PrepareProviderManager func(*testing.T, *providermanager.MockProvidermanager)

		RemoteAddr   string
		CategoryID   string
		PrepareToken func() string
		Redirect     string

		CheckToken       func(string)
		ExpectedRedirect string
		ExpectedErr      string
	}{
		"should handle the errors correctly": {
			PrepareDB:  func(m *r.Mock) {},
			PrepareAPI: func(c *sdk.MockSdk) {},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				uid := "90c658f3-0c9b-41b7-9710-44c98f74630f"
				name := "Néfix Estrada Campañá"
				empty := ""

				samlMock := provider.NewMockProvider(t)
				samlMock.On("GuessRole", mock.AnythingOfType("*context.cancelCtx"), &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      uid,
					Role:     nil,
					Group:    nil,
					Username: &uid,
					Name:     &name,
					Email:    &empty,
					Photo:    &empty,
				}, []string{
					"246e3ba9-1e16-4c23-aacc-98c99aef1a1a",
					"d7fea35e-0357-459b-8553-45a23d8cdacc",
					"26622f33-7a8a-46fa-ab89-286e5e8cb21f",
					"006bd007-a312-4647-88b2-9f09efb6ea97",
					"8c7f82f5-5a46-43d8-afd3-b96e4f182789",
					"23228d53-7d05-4a0a-ad00-dc703c5a20cf",
					"7e4e9835-f2df-4262-854b-01df5038ba34",
				}).Return(nil, &provider.ProviderError{
					User:   provider.ErrInvalidCredentials,
					Detail: errors.New("empty user role, no default"),
				})

				m.On("Provider", "saml", "default").Return(samlMock)
			},
			RemoteAddr: "127.0.0.1",
			CategoryID: "default",
			PrepareToken: func() string {
				uid := "90c658f3-0c9b-41b7-9710-44c98f74630f"
				name := "Néfix Estrada Campañá"
				empty := ""

				tkn, err := token.SignCategorySelectToken("", []*model.Category{{
					ID:    "test1",
					Name:  "Test 1",
					Photo: "",
				}, {
					ID:    "test2",
					Name:  "Test2",
					Photo: "",
				}}, nil, &[]string{
					"246e3ba9-1e16-4c23-aacc-98c99aef1a1a",
					"d7fea35e-0357-459b-8553-45a23d8cdacc",
					"26622f33-7a8a-46fa-ab89-286e5e8cb21f",
					"006bd007-a312-4647-88b2-9f09efb6ea97",
					"8c7f82f5-5a46-43d8-afd3-b96e4f182789",
					"23228d53-7d05-4a0a-ad00-dc703c5a20cf",
					"7e4e9835-f2df-4262-854b-01df5038ba34",
				}, &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      uid,
					Group:    nil,
					Username: &uid,
					Name:     &name,
					Email:    &empty,
					Photo:    &empty,
				})

				require.NoError(err)
				return tkn
			},
			ExpectedErr: "guess role from token: invalid credentials: empty user role, no default",
		},
		"should work without raw groups": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("test-category")).Return([]interface{}{
					map[string]interface{}{
						"id": "test-category",
					},
				}, nil)

				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix-uid"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "test-category"),
				))).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				role := model.RoleUser

				localMock := provider.NewMockProvider(t)
				localMock.On("GuessRole", mock.AnythingOfType("*context.cancelCtx"), &types.ProviderUserData{
					Provider: "local",
					Category: "test-category",
					UID:      "nefix-uid",
					Username: &username,
					Name:     &name,
					Email:    &email,
				}, []string{}).Return(&role, (*provider.ProviderError)(nil))
				localMock.On("SaveEmail").Return(true)
				localMock.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(false)

				m.On("Provider", "local", "test-category").Return(localMock)
			},
			RemoteAddr: "127.0.0.1",
			CategoryID: "test-category",
			PrepareToken: func() string {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				tkn, err := token.SignCategorySelectToken("", []*model.Category{{
					ID:   "test-category",
					Name: "Test Category",
				}}, nil, nil, &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
				})
				require.NoError(err)
				return tkn
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseRegisterToken("", ss)
				require.NoError(err)

				assert.Equal(t, "local", tkn.Provider)
				assert.Equal(t, "nefix-uid", tkn.UserID)
				assert.Equal(t, "test-category", tkn.CategoryID)
			},
			ExpectedRedirect: "/",
		},
		"should work with raw groups and successful GuessGroups": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("test-category")).Return([]interface{}{
					map[string]interface{}{
						"id": "test-category",
					},
				}, nil)

				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "saml-uid"),
					r.Eq(r.Row.Field("provider"), "saml"),
					r.Eq(r.Row.Field("category"), "test-category"),
				))).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				username := "saml-uid"
				name := "SAML User"
				email := "saml@example.org"
				empty := ""

				role := model.RoleUser

				samlMock := provider.NewMockProvider(t)
				samlMock.On("GuessGroups", mock.AnythingOfType("*context.cancelCtx"), &types.ProviderUserData{
					Provider: "saml",
					Category: "test-category",
					UID:      "saml-uid",
					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &empty,
				}, []string{"group1"}).Return(&model.Group{
					Category:      "test-category",
					ExternalAppID: "provider-saml",
					ExternalGID:   "group1",
					Name:          "Group 1",
				}, []*model.Group{}, (*provider.ProviderError)(nil))
				samlMock.On("GuessRole", mock.AnythingOfType("*context.cancelCtx"), &types.ProviderUserData{
					Provider: "saml",
					Category: "test-category",
					UID:      "saml-uid",
					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &empty,
				}, []string{}).Return(&role, (*provider.ProviderError)(nil))
				samlMock.On("SaveEmail").Return(true)
				samlMock.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(false)

				m.On("Provider", "saml", "test-category").Return(samlMock)
			},
			RemoteAddr: "127.0.0.1",
			CategoryID: "test-category",
			PrepareToken: func() string {
				username := "saml-uid"
				name := "SAML User"
				email := "saml@example.org"
				empty := ""

				tkn, err := token.SignCategorySelectToken("", []*model.Category{{
					ID:   "test-category",
					Name: "Test Category",
				}}, &[]string{"group1"}, nil, &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "saml-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &empty,
				})
				require.NoError(err)
				return tkn
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseRegisterToken("", ss)
				require.NoError(err)

				assert.Equal(t, "saml", tkn.Provider)
				assert.Equal(t, "saml-uid", tkn.UserID)
				assert.Equal(t, "test-category", tkn.CategoryID)
			},
			ExpectedRedirect: "/",
		},
		"should ignore ErrInvalidIDP from GuessRole": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("test-category")).Return([]interface{}{
					map[string]interface{}{
						"id": "test-category",
					},
				}, nil)

				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix-uid"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "test-category"),
				))).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *sdk.MockSdk) {},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				localMock := provider.NewMockProvider(t)
				localMock.On("GuessRole", mock.AnythingOfType("*context.cancelCtx"), &types.ProviderUserData{
					Provider: "local",
					Category: "test-category",
					UID:      "nefix-uid",
					Username: &username,
					Name:     &name,
					Email:    &email,
				}, []string{}).Return((*model.Role)(nil), &provider.ProviderError{
					User:   provider.ErrInvalidIDP,
					Detail: errors.New("provider does not support role guessing"),
				})
				localMock.On("SaveEmail").Return(true)
				localMock.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(false)

				m.On("Provider", "local", "test-category").Return(localMock)
			},
			RemoteAddr: "127.0.0.1",
			CategoryID: "test-category",
			PrepareToken: func() string {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				tkn, err := token.SignCategorySelectToken("", []*model.Category{{
					ID:   "test-category",
					Name: "Test Category",
				}}, nil, nil, &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
				})
				require.NoError(err)
				return tkn
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseRegisterToken("", ss)
				require.NoError(err)

				assert.Equal(t, "local", tkn.Provider)
				assert.Equal(t, "nefix-uid", tkn.UserID)
				assert.Equal(t, "test-category", tkn.CategoryID)
			},
			ExpectedRedirect: "/",
		},
		"should return error on invalid token": {
			PrepareDB:              func(m *r.Mock) {},
			PrepareAPI:             func(c *sdk.MockSdk) {},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {},

			RemoteAddr: "127.0.0.1",
			CategoryID: "default",
			PrepareToken: func() string {
				return "invalid-token"
			},

			ExpectedErr: "error parsing the JWT token: token is malformed: token contains an invalid number of segments",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			assert := assert.New(t)

			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			log := log.New("authentication-test", "debug")

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			apiMock := sdk.NewMockSdk(t)
			if tc.PrepareAPI != nil {
				tc.PrepareAPI(apiMock)
			}

			prvManagerMock := providermanager.NewMockProvidermanager(t)
			if tc.PrepareProviderManager != nil {
				tc.PrepareProviderManager(t, prvManagerMock)
			}

			a := &Authentication{
				Log:        log,
				Secret:     "",
				BaseURL:    &url.URL{Scheme: "https", Host: "localhost"},
				DB:         dbMock,
				API:        apiMock,
				prvManager: prvManagerMock,
			}

			tkn, redirect, err := a.finishCategorySelect(ctx, tc.RemoteAddr, tc.CategoryID, tc.PrepareToken(), tc.Redirect)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken == nil {
				assert.Empty(tkn)
			} else {
				tc.CheckToken(tkn)
			}
			assert.Equal(tc.ExpectedRedirect, redirect)

			dbMock.AssertExpectations(t)
			apiMock.AssertExpectations(t)
		})
	}
}
