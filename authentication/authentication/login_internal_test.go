package authentication

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"reflect"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/providermanager"
	"gitlab.com/isard/isardvdi/authentication/token"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestStartLogin(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB       func(*r.Mock)
		PrepareAPI      func(*apiv4.MockInvoker)
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
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					"default",
					"local",
				})).Return([]interface{}{}, nil)

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
			PrepareAPI: func(c *apiv4.MockInvoker) {},
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
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					"default",
					"mock",
				})).Return([]interface{}{}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "my group ID"),
				))).Return([]interface{}{}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "existing secondary group"),
				))).Return([]interface{}{
					map[string]interface{}{
						"id": "imagine an UUID here",
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
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
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCreateGroup", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.Name == "category" && req.ParentCategory.Value == "default" && req.ExternalGid.Value == "my group ID"
				})).Return(&apiv4.AdminGroup{
					ID:  "uuid here!",
					UID: "uuid here!",
				}, nil)
				c.On("AdminCreateGroup", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.Name == "category" && req.ParentCategory.Value == "default" && req.ExternalGid.Value == "other secondary group"
				})).Return(&apiv4.AdminGroup{
					ID:  "uuid here!",
					UID: "uuid here!",
				}, nil)
				c.On("AdminAutoRegister", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req *apiv4.AutoRegisterRequest) bool {
					return req.RoleID == "advanced" && req.GroupID == "uuid here!"
				}), mock.AnythingOfType("apiv4.AdminAutoRegisterParams")).Return(&apiv4.AutoRegisterResponse{ID: "user ID"}, nil)
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user ID"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user ID"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user ID"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckPasswordResetRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckPasswordResetRequiredParams{UserID: "user ID"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
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
			PrepareAPI: func(c *apiv4.MockInvoker) {},

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
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					uuid.Max.String(),
					"default",
					"local",
				})).Return([]interface{}{}, nil)

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
			PrepareAPI: func(s *apiv4.MockInvoker) {},
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
			PrepareAPI: func(c *apiv4.MockInvoker) {},

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
			PrepareAPI: func(c *apiv4.MockInvoker) {},

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
			PrepareAPI: func(c *apiv4.MockInvoker) {},

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"admin",
					"default",
					"local",
				})).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"admin",
					"default",
					"local",
				})).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					"default",
					"local",
				})).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					"default",
					"ldap",
				})).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					"default",
					"local",
				})).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
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
			PrepareAPI: func(c *apiv4.MockInvoker) {},

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
			PrepareAPI: func(c *apiv4.MockInvoker) {},

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
			PrepareAPI: func(c *apiv4.MockInvoker) {},

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
			PrepareAPI: func(c *apiv4.MockInvoker) {},

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
		"should update the normalized name when the provider sends a new one": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "default-default",
						"secondary_groups":         []string{},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"accessed":                 float64(0),
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)

				m.On(r.Table("users").Get("user-resync-1").Update(map[string]interface{}{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "nefix",
					"password":                 "",
					"password_reset_token":     "",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "advanced",
					"group":                    "default-default",
					"secondary_groups":         []string{},
					"name":                     "New Name",
					"email":                    "old@example.com",
					"email_verified":           verified,
					"email_verification_token": "verify-token",
					"photo":                    "old-photo.png",
					"accessed":                 float64(0),
					"disclaimer_acknowledged":  true,
					"api_key":                  "",
				})).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "New \xffName"
				email := "old@example.com"
				photo := "old-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-resync-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should not overwrite the stored name when the provider sends an empty one": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "default-default",
						"secondary_groups":         []string{},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"accessed":                 float64(0),
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := ""
				email := "old@example.com"
				photo := "old-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-resync-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should update the username when the provider sends a new one": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "default-default",
						"secondary_groups":         []string{},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"accessed":                 float64(0),
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)

				m.On(r.Table("users").Get("user-resync-1").Update(map[string]interface{}{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "nefixnew",
					"password":                 "",
					"password_reset_token":     "",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "advanced",
					"group":                    "default-default",
					"secondary_groups":         []string{},
					"name":                     "Néfix Estrada",
					"email":                    "old@example.com",
					"email_verified":           verified,
					"email_verification_token": "verify-token",
					"photo":                    "old-photo.png",
					"accessed":                 float64(0),
					"disclaimer_acknowledged":  true,
					"api_key":                  "",
				})).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefixnew"
				name := "Néfix Estrada"
				email := "old@example.com"
				photo := "old-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-resync-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should update the photo when the provider sends a new one": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "default-default",
						"secondary_groups":         []string{},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"accessed":                 float64(0),
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)

				m.On(r.Table("users").Get("user-resync-1").Update(map[string]interface{}{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "nefix",
					"password":                 "",
					"password_reset_token":     "",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "advanced",
					"group":                    "default-default",
					"secondary_groups":         []string{},
					"name":                     "Néfix Estrada",
					"email":                    "old@example.com",
					"email_verified":           verified,
					"email_verification_token": "verify-token",
					"photo":                    "new-photo.png",
					"accessed":                 float64(0),
					"disclaimer_acknowledged":  true,
					"api_key":                  "",
				})).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"
				photo := "new-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-resync-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should update the email and reset its verification when the provider sends a new one": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "default-default",
						"secondary_groups":         []string{},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"accessed":                 float64(0),
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)

				m.On(r.Table("users").Get("user-resync-1").Update(map[string]interface{}{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "nefix",
					"password":                 "",
					"password_reset_token":     "",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "advanced",
					"group":                    "default-default",
					"secondary_groups":         []string{},
					"name":                     "Néfix Estrada",
					"email":                    "new@example.com",
					"email_verified":           nil,
					"email_verification_token": "",
					"photo":                    "old-photo.png",
					"accessed":                 float64(0),
					"disclaimer_acknowledged":  true,
					"api_key":                  "",
				})).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "new@example.com"
				photo := "old-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-resync-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should update the role when the provider sends a new one": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "default-default",
						"secondary_groups":         []string{},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"accessed":                 float64(0),
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)

				m.On(r.Table("users").Get("user-resync-1").Update(map[string]interface{}{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "nefix",
					"password":                 "",
					"password_reset_token":     "",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "manager",
					"group":                    "default-default",
					"secondary_groups":         []string{},
					"name":                     "Néfix Estrada",
					"email":                    "old@example.com",
					"email_verified":           verified,
					"email_verification_token": "verify-token",
					"photo":                    "old-photo.png",
					"accessed":                 float64(0),
					"disclaimer_acknowledged":  true,
					"api_key":                  "",
				})).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				role := model.RoleManager
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"
				photo := "old-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Role:     &role,
					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-resync-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should update the group when the provider maps a different existing one": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "old-group-id",
						"secondary_groups":         []string{},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"accessed":                 float64(0),
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "new group"),
				))).Return([]interface{}{
					map[string]interface{}{
						"id": "new-group-id",
					},
				}, nil)

				m.On(r.Table("users").Get("user-resync-1").Update(map[string]interface{}{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "nefix",
					"password":                 "",
					"password_reset_token":     "",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "advanced",
					"group":                    "new-group-id",
					"secondary_groups":         []string{},
					"name":                     "Néfix Estrada",
					"email":                    "old@example.com",
					"email_verified":           verified,
					"email_verification_token": "verify-token",
					"photo":                    "old-photo.png",
					"accessed":                 float64(0),
					"disclaimer_acknowledged":  true,
					"api_key":                  "",
				})).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "new group",
				Name:          "category",
				Description:   "some description",
			},
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"
				photo := "old-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-resync-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should auto-register and update a group the provider maps that does not exist yet": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "old-group-id",
						"secondary_groups":         []string{},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"accessed":                 float64(0),
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "new group"),
				))).Return([]interface{}{}, nil)

				m.On(r.Table("users").Get("user-resync-1").Update(map[string]interface{}{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "nefix",
					"password":                 "",
					"password_reset_token":     "",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "advanced",
					"group":                    "created-group-id",
					"secondary_groups":         []string{},
					"name":                     "Néfix Estrada",
					"email":                    "old@example.com",
					"email_verified":           verified,
					"email_verification_token": "verify-token",
					"photo":                    "old-photo.png",
					"accessed":                 float64(0),
					"disclaimer_acknowledged":  true,
					"api_key":                  "",
				})).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCreateGroup", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.Name == "category" && req.ParentCategory.Value == "default" && req.ExternalGid.Value == "new group"
				})).Return(&apiv4.AdminGroup{
					ID:  "created-group-id",
					UID: "created-group-id",
				}, nil)
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "new group",
				Name:          "category",
				Description:   "some description",
			},
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"
				photo := "old-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-resync-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should update the secondary groups when the provider maps different ones": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "primary-id",
						"secondary_groups":         []string{"old-secondary-id"},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"accessed":                 float64(0),
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "new secondary group"),
				))).Return([]interface{}{
					map[string]interface{}{
						"id": "new-secondary-id",
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "primary group"),
				))).Return([]interface{}{
					map[string]interface{}{
						"id": "primary-id",
					},
				}, nil)

				m.On(r.Table("users").Get("user-resync-1").Update(map[string]interface{}{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "nefix",
					"password":                 "",
					"password_reset_token":     "",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "advanced",
					"group":                    "primary-id",
					"secondary_groups":         []string{"new-secondary-id"},
					"name":                     "Néfix Estrada",
					"email":                    "old@example.com",
					"email_verified":           verified,
					"email_verification_token": "verify-token",
					"photo":                    "old-photo.png",
					"accessed":                 float64(0),
					"disclaimer_acknowledged":  true,
					"api_key":                  "",
				})).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "primary group",
				Name:          "category",
				Description:   "some description",
			},
			SecondaryGroups: []*model.Group{{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "new secondary group",
				Name:          "category",
				Description:   "some description",
			}},
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"
				photo := "old-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-resync-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should return an error if checking whether the user exists fails": {
			PrepareDB: func(m *r.Mock) {
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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return(nil, fmt.Errorf("find error"))
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(false)
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			ExpectedErr: "check if user exists: find error",
		},
		"should return an error if checking the mapped group fails": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "old-group-id",
						"secondary_groups":         []string{},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "new group"),
				))).Return(nil, fmt.Errorf("group error"))
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "new group",
				Name:          "category",
				Description:   "some description",
			},
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"
				photo := "old-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			ExpectedErr: "check if group exists: group error",
		},
		"should return an error if auto-registering the mapped group fails": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "old-group-id",
						"secondary_groups":         []string{},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "new group"),
				))).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCreateGroup", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.Name == "category" && req.ParentCategory.Value == "default" && req.ExternalGid.Value == "new group"
				})).Return(nil, fmt.Errorf("create error"))
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "new group",
				Name:          "category",
				Description:   "some description",
			},
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"
				photo := "old-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			ExpectedErr: "auto register group: register the group: create error",
		},
		"should return an error if checking the group fails during registration": {
			PrepareDB: func(m *r.Mock) {
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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "new group"),
				))).Return(nil, fmt.Errorf("group error"))
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "new group",
				Name:          "category",
				Description:   "some description",
			},
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			ExpectedErr: "check if group exists: group error",
		},
		"should return an error if registering the group fails during registration": {
			PrepareDB: func(m *r.Mock) {
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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "new group"),
				))).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCreateGroup", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.Name == "category" && req.ParentCategory.Value == "default" && req.ExternalGid.Value == "new group"
				})).Return(nil, fmt.Errorf("create error"))
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "new group",
				Name:          "category",
				Description:   "some description",
			},
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			ExpectedErr: "auto register group: register the group: create error",
		},
		"should return an error if registering the user fails": {
			PrepareDB: func(m *r.Mock) {
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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminAutoRegister", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req *apiv4.AutoRegisterRequest) bool {
					return req.RoleID == "advanced"
				}), mock.AnythingOfType("apiv4.AdminAutoRegisterParams")).Return(nil, fmt.Errorf("register error"))
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				role := model.RoleAdvanced
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Role:     &role,
					Username: &username,
					Name:     &name,
					Email:    &email,
				}
			},
			Redirect: "/",

			ExpectedErr: "auto register user: register the user: register error",
		},
		"should return an error if updating the existing user fails": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]interface{}{
					map[string]interface{}{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "advanced",
						"group":                    "default-default",
						"secondary_groups":         []string{},
						"name":                     "Néfix Estrada",
						"email":                    "old@example.com",
						"email_verified":           verified,
						"email_verification_token": "verify-token",
						"photo":                    "old-photo.png",
						"accessed":                 float64(0),
						"disclaimer_acknowledged":  true,
						"api_key":                  "",
					},
				}, nil)

				m.On(r.Table("users").Get("user-resync-1").Update(map[string]interface{}{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "nefix",
					"password":                 "",
					"password_reset_token":     "",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "advanced",
					"group":                    "default-default",
					"secondary_groups":         []string{},
					"name":                     "Néfix Estrada",
					"email":                    "new@example.com",
					"email_verified":           nil,
					"email_verification_token": "",
					"photo":                    "old-photo.png",
					"accessed":                 float64(0),
					"disclaimer_acknowledged":  true,
					"api_key":                  "",
				})).Return(nil, fmt.Errorf("update error"))
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "new@example.com"
				photo := "old-photo.png"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
				}
			},
			Redirect: "/",

			ExpectedErr: "update user: update error",
		},
		"should refresh every provider-owned field on re-login": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

				dbUser := map[string]any{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "old-username",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "advanced",
					"group":                    "old-group-id",
					"secondary_groups":         []string{"old-secondary-id"},
					"password":                 "old-password",
					"password_reset_token":     "old-reset-token",
					"name":                     "Old Name",
					"email":                    "old@example.com",
					"email_verified":           verified,
					"email_verification_token": "verify-token",
					"photo":                    "old-photo.png",
					"disclaimer_acknowledged":  true,
					"accessed":                 float64(123),
					"api_key":                  "old-api-key",
				}

				expected := map[string]any{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "new-username",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "manager",
					"group":                    "new-group-id",
					"secondary_groups":         []string{"new-secondary-id"},
					"password":                 "old-password",
					"password_reset_token":     "old-reset-token",
					"name":                     "New Name",
					"email":                    "new@example.com",
					"email_verified":           nil,
					"email_verification_token": "",
					"photo":                    "new-photo.png",
					"disclaimer_acknowledged":  true,
					"accessed":                 float64(123),
					"api_key":                  "old-api-key",
				}

				userType := reflect.TypeFor[model.User]()
				for i := range userType.NumField() {
					field := userType.Field(i)
					tag := field.Tag.Get("rethinkdb")
					if _, ok := expected[tag]; ok {
						continue
					}

					assert.Failf("uncovered model.User field", "the re-login sync test doesn't cover %q (rethinkdb:%q)", field.Name, tag)
					zero := reflect.Zero(field.Type).Interface()
					dbUser[tag] = zero
					expected[tag] = zero
				}

				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
						"authentication": map[string]any{
							"local": map[string]any{
								"email_domain_restriction": map[string]any{"enabled": false},
							},
						},
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{dbUser}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "primary group"),
				))).Return([]any{map[string]any{"id": "new-group-id"}}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "secondary group"),
				))).Return([]any{map[string]any{"id": "new-secondary-id"}}, nil)

				m.On(r.Table("users").Get("user-resync-1").Update(expected)).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "primary group",
				Name:          "category",
				Description:   "some description",
			},
			SecondaryGroups: []*model.Group{{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "secondary group",
				Name:          "category-secondary",
				Description:   "some description",
			}},
			ProviderUserData: func() *types.ProviderUserData {
				username := "new-username"
				name := "New Name"
				email := "new@example.com"
				photo := "new-photo.png"
				role := model.Role("manager")

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Username: &username,
					Name:     &name,
					Email:    &email,
					Photo:    &photo,
					Role:     &role,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-resync-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()

			log := log.New("authentication-test", "debug")

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			apiMock := apiv4.NewMockInvoker(t)
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
		PrepareAPI             func(*apiv4.MockInvoker)
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
			PrepareAPI: func(c *apiv4.MockInvoker) {},
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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"test-category",
					"local",
				})).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"saml-uid",
					"test-category",
					"saml",
				})).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
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

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []interface{}{
					"nefix-uid",
					"test-category",
					"local",
				})).Return([]interface{}{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
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
			PrepareAPI:             func(c *apiv4.MockInvoker) {},
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

			apiMock := apiv4.NewMockInvoker(t)
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
