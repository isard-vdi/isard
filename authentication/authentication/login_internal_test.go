package authentication

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"reflect"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/providermanager"
	"gitlab.com/isard/isardvdi/authentication/token"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"go.nhat.io/grpcmock"
	"google.golang.org/grpc/codes"
	"google.golang.org/protobuf/types/known/timestamppb"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestStartLogin(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB              func(*r.Mock)
		PrepareAPI             func(*apiv4.MockInvoker)
		PrepareSessions        func(*grpcmock.Server)
		PrepareProvider        func(*provider.MockProvider)
		PrepareProviderManager func(*testing.T, *providermanager.MockProvidermanager)

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
				p.On("String").Return("local")
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
				p.On("String").Return("mock")
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
				p.On("String").Return("local")
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
				p.On("String").Return("local")
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
				p.On("String").Return("local")
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
				p.On("String").Return("local")
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
				p.On("String").Return("ldap")
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
				p.On("String").Return("local")
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
				p.On("String").Return("saml")
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
				p.On("String").Return("saml")
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
				p.On("String").Return("saml")
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
				p.On("String").Return("saml")
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
				p.On("String").Return("saml")
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
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminUpdateUser", mock.AnythingOfType("context.backgroundCtx"), &apiv4.AdminUserUpdateData{
					Role: apiv4.NewOptNilString("manager"),
				}, apiv4.AdminUpdateUserParams{UserID: "user-resync-1"}).Return(&apiv4.AdminUpdateUserNoContent{}, nil)

				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)
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
		"should update the role and group when the guessed role is in the autoregister roles even if the stored role is not": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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
				})).Return([]any{
					map[string]any{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "manager",
						"group":                    "manual-group-id",
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
				))).Return([]any{
					map[string]any{
						"id": "new-group-id",
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminUpdateUser", mock.AnythingOfType("context.backgroundCtx"), &apiv4.AdminUserUpdateData{
					Role:            apiv4.NewOptNilString("user"),
					Group:           apiv4.NewOptNilString("new-group-id"),
					SecondaryGroups: apiv4.NewOptNilStringArray([]string{}),
				}, apiv4.AdminUpdateUserParams{UserID: "user-resync-1"}).Return(&apiv4.AdminUpdateUserNoContent{}, nil)

				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleUser
				})).Return(true)
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
				role := model.RoleUser
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
		"should sign a re-register token when the guessed role is outside the autoregister roles but the stored one is not": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":   "user-resync-1",
						"role": "user",
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleManager
				})).Return(false)
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleUser
				})).Return(true)
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
				tkn, err := token.ParseReRegisterToken("", ss)
				require.NoError(err)

				assert.Equal("saml", tkn.Provider)
				assert.Equal("nefix-uid", tkn.UserID)
				assert.Equal("default", tkn.CategoryID)
				assert.Equal("manager", tkn.RoleID)
			},
			ExpectedRedirect: "/",
		},
		"should ask the authenticating provider and not the form wrapper when syncing the role and group on a form re-login": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"ldap",
				})).Return([]any{
					map[string]any{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "ldap",
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
					r.Eq(r.Row.Field("external_app_id"), "provider-ldap"),
					r.Eq(r.Row.Field("external_gid"), "new group"),
				))).Return([]any{
					map[string]any{
						"id": "new-group-id",
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminUpdateUser", mock.AnythingOfType("context.backgroundCtx"), &apiv4.AdminUserUpdateData{
					Role:            apiv4.NewOptNilString("manager"),
					Group:           apiv4.NewOptNilString("new-group-id"),
					SecondaryGroups: apiv4.NewOptNilStringArray([]string{}),
				}, apiv4.AdminUpdateUserParams{UserID: "user-resync-1"}).Return(&apiv4.AdminUpdateUserNoContent{}, nil)

				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("String").Return("form")
			},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				ldapMock := provider.NewMockProvider(t)
				ldapMock.On("SaveEmail").Return(true)
				ldapMock.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)

				m.On("Provider", "ldap", "default").Return(ldapMock)
			},

			Provider:   "form",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-ldap",
				ExternalGID:   "new group",
				Name:          "category",
				Description:   "some description",
			},
			ProviderUserData: func() *types.ProviderUserData {
				role := model.RoleManager

				return &types.ProviderUserData{
					Provider: "ldap",
					Category: "default",
					UID:      "nefix-uid",

					Role: &role,
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
		"should sign a re-register token with the authenticating provider when the guessed role is denied on a form re-login": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"ldap",
				})).Return([]any{
					map[string]any{
						"id":   "user-resync-1",
						"role": "user",
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("String").Return("form")
			},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				ldapMock := provider.NewMockProvider(t)
				ldapMock.On("SaveEmail").Return(true)
				ldapMock.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleManager
				})).Return(false)
				ldapMock.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleUser
				})).Return(true)

				m.On("Provider", "ldap", "default").Return(ldapMock)
			},

			Provider:   "form",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				role := model.RoleManager
				username := "nefix"

				return &types.ProviderUserData{
					Provider: "ldap",
					Category: "default",
					UID:      "nefix-uid",

					Role:     &role,
					Username: &username,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseReRegisterToken("", ss)
				require.NoError(err)

				assert.Equal("ldap", tkn.Provider)
				assert.Equal("nefix-uid", tkn.UserID)
				assert.Equal("default", tkn.CategoryID)
				assert.Equal("manager", tkn.RoleID)
			},
			ExpectedRedirect: "/",
		},
		"should ask the local provider and not the form wrapper on a local form re-login": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"local",
				})).Return([]any{
					map[string]any{
						"id":     "user-resync-1",
						"active": true,
						"role":   "user",
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("String").Return("form")
			},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				localMock := provider.NewMockProvider(t)
				localMock.On("SaveEmail").Return(true)
				localMock.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleUser
				})).Return(false)

				m.On("Provider", "local", "default").Return(localMock)
			},

			Provider:   "form",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				role := model.RoleUser

				return &types.ProviderUserData{
					Provider: "local",
					Category: "default",
					UID:      "nefix-uid",

					Role: &role,
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
		"should sign a register token if the user is missing and the authenticating provider denies the autoregister on a form login": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"ldap",
				})).Return([]any{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("String").Return("form")
			},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				ldapMock := provider.NewMockProvider(t)
				ldapMock.On("SaveEmail").Return(true)
				ldapMock.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(false)

				m.On("Provider", "ldap", "default").Return(ldapMock)
			},

			Provider:   "form",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				username := "nefix"
				name := "Néfix Estrada"
				email := "nefix@example.org"

				return &types.ProviderUserData{
					Provider: "ldap",
					Category: "default",
					UID:      "nefix-uid",

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
				assert.Equal("nefix-uid", tkn.UserID)
				assert.Equal("nefix", tkn.Username)
				assert.Equal("default", tkn.CategoryID)
				assert.Equal("Néfix Estrada", tkn.Name)
				assert.Equal("nefix@example.org", tkn.Email)
			},
			ExpectedRedirect: "/",
		},
		"should autoregister a missing user with the authenticating provider on a form login": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"ldap",
				})).Return([]any{}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-ldap"),
					r.Eq(r.Row.Field("external_gid"), "new group"),
				))).Return([]any{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCreateGroup", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.Name == "category" && req.ParentCategory.Value == "default" && req.ExternalGid.Value == "new group"
				})).Return(&apiv4.AdminGroup{
					ID:  "new-group-id",
					UID: "new-group-id",
				}, nil)
				c.On("AdminAutoRegister", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req *apiv4.AutoRegisterRequest) bool {
					return req.RoleID == "advanced" && req.GroupID == "new-group-id" && !req.SecondaryGroups.Set
				}), mock.AnythingOfType("apiv4.AdminAutoRegisterParams")).Return(&apiv4.AutoRegisterResponse{ID: "registered-id"}, nil)
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "registered-id"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("String").Return("form")
			},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				ldapMock := provider.NewMockProvider(t)
				ldapMock.On("SaveEmail").Return(true)
				ldapMock.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)

				m.On("Provider", "ldap", "default").Return(ldapMock)
			},

			Provider:   "form",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-ldap",
				ExternalGID:   "new group",
				Name:          "category",
				Description:   "some description",
			},
			ProviderUserData: func() *types.ProviderUserData {
				role := model.RoleAdvanced

				return &types.ProviderUserData{
					Provider: "ldap",
					Category: "default",
					UID:      "nefix-uid",

					Role: &role,
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("registered-id", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should keep the stored role and group in the update when the photo changes and both roles are outside the autoregister roles": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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
				})).Return([]any{
					map[string]any{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "manager",
						"group":                    "manual-group-id",
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

				m.On(r.Table("users").Get("user-resync-1").Update(map[string]any{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "nefix",
					"password":                 "",
					"password_reset_token":     "",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "manager",
					"group":                    "manual-group-id",
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
				p.On("String").Return("saml")
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleAdvanced
				})).Return(false)
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleManager
				})).Return(false)
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
				role := model.RoleAdvanced
				username := "nefix"
				name := "Néfix Estrada"
				email := "old@example.com"
				photo := "new-photo.png"

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
		"should keep the stored role and group when finishing the login and both roles are outside the autoregister roles": {
			PrepareDB: func(m *r.Mock) {
				verified := float64(1700000000)

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
				})).Return([]any{
					map[string]any{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "manager",
						"group":                    "manual-group-id",
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

				m.On(r.Table("users").Get("user-resync-1")).Return([]any{
					map[string]any{
						"id":                       "user-resync-1",
						"uid":                      "nefix-uid",
						"username":                 "nefix",
						"password":                 "",
						"password_reset_token":     "",
						"provider":                 "saml",
						"active":                   true,
						"category":                 "default",
						"role":                     "manager",
						"group":                    "manual-group-id",
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

				m.On(r.Table("users").Get("user-resync-1").Update(map[string]any{
					"id":                       "user-resync-1",
					"uid":                      "nefix-uid",
					"username":                 "nefix",
					"password":                 "",
					"password_reset_token":     "",
					"provider":                 "saml",
					"active":                   true,
					"category":                 "default",
					"role":                     "manager",
					"group":                    "manual-group-id",
					"secondary_groups":         []string{},
					"name":                     "Néfix Estrada",
					"email":                    "old@example.com",
					"email_verified":           verified,
					"email_verification_token": "verify-token",
					"photo":                    "old-photo.png",
					"accessed":                 r.MockAnything(),
					"disclaimer_acknowledged":  true,
					"api_key":                  "",
				})).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckPasswordResetRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckPasswordResetRequiredParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminGetUserNotificationDisplays", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminGetUserNotificationDisplaysParams{UserID: "user-resync-1", Trigger: apiv4.NotificationTriggerEnumLogin}).Return(&apiv4.AdminUserDisplaysResponse{Displays: []apiv4.NotificationDisplayEnum{}}, nil)
			},
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/New").WithPayload(&sessionsv1.NewRequest{
					UserId:     "user-resync-1",
					RemoteAddr: "127.0.0.1",
				}).Return(&sessionsv1.NewResponse{
					Id: "ThoJuroQueEsUnID",
					Time: &sessionsv1.NewResponseTime{
						MaxTime:        timestamppb.New(time.Now().Add(8 * time.Hour)),
						MaxRenewTime:   timestamppb.New(time.Now().Add(30 * time.Minute)),
						ExpirationTime: timestamppb.New(time.Now().Add(5 * time.Minute)),
					},
				})
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleAdvanced
				})).Return(false)
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleManager
				})).Return(false)
			},

			RemoteAddr: "127.0.0.1",
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
				role := model.RoleAdvanced
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
				tkn, err := token.ParseLoginToken("", ss)
				require.NoError(err)

				assert.Equal(token.LoginClaimsData{
					Provider:   "saml",
					ID:         "user-resync-1",
					RoleID:     "manager",
					CategoryID: "default",
					GroupID:    "manual-group-id",
					Name:       "Néfix Estrada",
				}, tkn.Data)
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
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminUpdateUser", mock.AnythingOfType("context.backgroundCtx"), &apiv4.AdminUserUpdateData{
					Group:           apiv4.NewOptNilString("new-group-id"),
					SecondaryGroups: apiv4.NewOptNilStringArray([]string{}),
				}, apiv4.AdminUpdateUserParams{UserID: "user-resync-1"}).Return(&apiv4.AdminUpdateUserNoContent{}, nil)

				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
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
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCreateGroup", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.Name == "category" && req.ParentCategory.Value == "default" && req.ExternalGid.Value == "new group"
				})).Return(&apiv4.AdminGroup{
					ID:  "created-group-id",
					UID: "created-group-id",
				}, nil)
				c.On("AdminUpdateUser", mock.AnythingOfType("context.backgroundCtx"), &apiv4.AdminUserUpdateData{
					Group:           apiv4.NewOptNilString("created-group-id"),
					SecondaryGroups: apiv4.NewOptNilStringArray([]string{}),
				}, apiv4.AdminUpdateUserParams{UserID: "user-resync-1"}).Return(&apiv4.AdminUpdateUserNoContent{}, nil)
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
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
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminUpdateUser", mock.AnythingOfType("context.backgroundCtx"), &apiv4.AdminUserUpdateData{
					Group:           apiv4.NewOptNilString("primary-id"),
					SecondaryGroups: apiv4.NewOptNilStringArray([]string{"new-secondary-id"}),
				}, apiv4.AdminUpdateUserParams{UserID: "user-resync-1"}).Return(&apiv4.AdminUpdateUserNoContent{}, nil)

				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)
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
		"should not call apiv4 when neither the role nor the groups change": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":               "user-resync-1",
						"uid":              "nefix-uid",
						"provider":         "saml",
						"active":           true,
						"category":         "default",
						"role":             "advanced",
						"group":            "primary-id",
						"secondary_groups": []string{"secondary-id"},
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "secondary group"),
				))).Return([]any{
					map[string]any{
						"id": "secondary-id",
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-saml"),
					r.Eq(r.Row.Field("external_gid"), "primary group"),
				))).Return([]any{
					map[string]any{
						"id": "primary-id",
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			Group: &model.Group{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "primary group",
				Name:          "category",
			},
			SecondaryGroups: []*model.Group{{
				Category:      "default",
				ExternalAppID: "provider-saml",
				ExternalGID:   "secondary group",
				Name:          "category",
			}},
			ProviderUserData: func() *types.ProviderUserData {
				role := model.RoleAdvanced

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Role: &role,
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
				p.On("String").Return("saml")
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
				p.On("String").Return("saml")
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
				p.On("String").Return("saml")
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
		"should not call apiv4 if checking the mapped group fails after the role changed": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":       "user-resync-1",
						"uid":      "nefix-uid",
						"provider": "saml",
						"active":   true,
						"category": "default",
						"role":     "advanced",
						"group":    "old-group-id",
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
				p.On("String").Return("saml")
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
				role := model.RoleManager

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Role: &role,
				}
			},
			Redirect: "/",

			ExpectedErr: "check if group exists: group error",
		},
		"should not update the user in the database if updating it through apiv4 fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":       "user-resync-1",
						"uid":      "nefix-uid",
						"provider": "saml",
						"active":   true,
						"category": "default",
						"role":     "advanced",
						"group":    "default-default",
						"name":     "Old Name",
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminUpdateUser", mock.AnythingOfType("context.backgroundCtx"), &apiv4.AdminUserUpdateData{
					Role: apiv4.NewOptNilString("manager"),
				}, apiv4.AdminUpdateUserParams{UserID: "user-resync-1"}).Return(nil, fmt.Errorf("update error"))
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				role := model.RoleManager
				name := "New Name"

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Role: &role,
					Name: &name,
				}
			},
			Redirect: "/",

			ExpectedErr: "sync the role and groups through apiv4: update error",
		},
		"should return an error if updating the user through apiv4 returns an unexpected response": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":       "user-resync-1",
						"uid":      "nefix-uid",
						"provider": "saml",
						"active":   true,
						"category": "default",
						"role":     "advanced",
						"group":    "default-default",
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminUpdateUser", mock.AnythingOfType("context.backgroundCtx"), &apiv4.AdminUserUpdateData{
					Role: apiv4.NewOptNilString("manager"),
				}, apiv4.AdminUpdateUserParams{UserID: "user-resync-1"}).Return(&apiv4.AdminUpdateUserUnauthorized{
					Error:       "unauthorized",
					Description: "invalid session",
				}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				role := model.RoleManager

				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",

					Role: &role,
				}
			},
			Redirect: "/",

			ExpectedErr: "sync the role and groups through apiv4: ogen 401 unauthorized: invalid session []",
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
				p.On("String").Return("saml")
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
				p.On("String").Return("saml")
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
				p.On("String").Return("saml")
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
				p.On("String").Return("saml")
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
				c.On("AdminUpdateUser", mock.AnythingOfType("context.backgroundCtx"), &apiv4.AdminUserUpdateData{
					Role:            apiv4.NewOptNilString("manager"),
					Group:           apiv4.NewOptNilString("new-group-id"),
					SecondaryGroups: apiv4.NewOptNilStringArray([]string{"new-secondary-id"}),
				}, apiv4.AdminUpdateUserParams{UserID: "user-resync-1"}).Return(&apiv4.AdminUpdateUserNoContent{}, nil)

				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-resync-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
				p.On("AutoRegister", mock.AnythingOfType("*model.User")).Return(true)
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
		"should redirect to the login notifications page if the user has fullpage notifications pending": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)

				m.On(r.Table("users").Get("user-1")).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)

				m.On(r.Table("users").Get("user-1").Update(r.MockAnything())).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckPasswordResetRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckPasswordResetRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminGetUserNotificationDisplays", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminGetUserNotificationDisplaysParams{UserID: "user-1", Trigger: apiv4.NotificationTriggerEnumLogin}).Return(&apiv4.AdminUserDisplaysResponse{Displays: []apiv4.NotificationDisplayEnum{apiv4.NotificationDisplayEnumFullpage}}, nil)
			},
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/New").WithPayload(&sessionsv1.NewRequest{
					UserId:     "user-1",
					RemoteAddr: "127.0.0.1",
				}).Return(&sessionsv1.NewResponse{
					Id: "ThoJuroQueEsUnID",
					Time: &sessionsv1.NewResponseTime{
						MaxTime:        timestamppb.New(time.Now().Add(8 * time.Hour)),
						MaxRenewTime:   timestamppb.New(time.Now().Add(30 * time.Minute)),
						ExpirationTime: timestamppb.New(time.Now().Add(5 * time.Minute)),
					},
				})
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			RemoteAddr: "127.0.0.1",
			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			CheckToken: func(ss string) {
				tkn, err := token.ParseLoginToken("", ss)
				require.NoError(err)

				assert.Equal("user-1", tkn.Data.ID)
			},
			ExpectedRedirect: "/notifications/login",
		},
		"should return an error if checking the disclaimer fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(nil, fmt.Errorf("disclaimer error"))
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "check if the user needs to accept the disclaimer: disclaimer error",
		},
		"should return an error if the disclaimer check returns an unexpected response": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.AdminCheckDisclaimerUnauthorized{}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "check if the user needs to accept the disclaimer: unexpected response type *apiv4.AdminCheckDisclaimerUnauthorized",
		},
		"should return an error if checking the migration fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(nil, fmt.Errorf("migration error"))
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "check if the user needs to migrate: migration error",
		},
		"should return an error if the migration check returns an unexpected response": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(&apiv4.AdminCheckMigrationRequiredUnauthorized{}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "check if the user needs to migrate: unexpected response type *apiv4.AdminCheckMigrationRequiredUnauthorized",
		},
		"should return an error if checking the email verification fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user-1"}).Return(nil, fmt.Errorf("email error"))
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "check if the user needs to verify the email: email error",
		},
		"should return an error if the email verification check returns an unexpected response": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user-1"}).Return(&apiv4.AdminCheckEmailVerificationUnauthorized{}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "check if the user needs to verify the email: unexpected response type *apiv4.AdminCheckEmailVerificationUnauthorized",
		},
		"should return an error if checking the password reset fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckPasswordResetRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckPasswordResetRequiredParams{UserID: "user-1"}).Return(nil, fmt.Errorf("password error"))
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "check if the user needs to reset the password: password error",
		},
		"should return an error if the password reset check returns an unexpected response": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckPasswordResetRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckPasswordResetRequiredParams{UserID: "user-1"}).Return(&apiv4.AdminCheckPasswordResetRequiredUnauthorized{}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "check if the user needs to reset the password: unexpected response type *apiv4.AdminCheckPasswordResetRequiredUnauthorized",
		},
		"should return an error if loading the rest of the user data fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)

				m.On(r.Table("users").Get("user-1")).Return(nil, fmt.Errorf("load error"))
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckPasswordResetRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckPasswordResetRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "load user from DB: load error",
		},
		"should return an error if updating the user with the latest data fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)

				m.On(r.Table("users").Get("user-1")).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)

				m.On(r.Table("users").Get("user-1").Update(r.MockAnything())).Return(nil, fmt.Errorf("update error"))
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckPasswordResetRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckPasswordResetRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "update user in the DB: update error",
		},
		"should return an error if creating the session fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)

				m.On(r.Table("users").Get("user-1")).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)

				m.On(r.Table("users").Get("user-1").Update(r.MockAnything())).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckPasswordResetRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckPasswordResetRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
			},
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/New").WithPayload(&sessionsv1.NewRequest{
					UserId:     "user-1",
					RemoteAddr: "127.0.0.1",
				}).ReturnError(codes.Unavailable, "session error")
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			RemoteAddr: "127.0.0.1",
			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "create the session: rpc error: code = Unavailable desc = session error",
		},
		"should return an error if checking the pending notifications fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)

				m.On(r.Table("users").Get("user-1")).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)

				m.On(r.Table("users").Get("user-1").Update(r.MockAnything())).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckPasswordResetRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckPasswordResetRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminGetUserNotificationDisplays", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminGetUserNotificationDisplaysParams{UserID: "user-1", Trigger: apiv4.NotificationTriggerEnumLogin}).Return(nil, fmt.Errorf("notifications error"))
			},
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/New").WithPayload(&sessionsv1.NewRequest{
					UserId:     "user-1",
					RemoteAddr: "127.0.0.1",
				}).Return(&sessionsv1.NewResponse{
					Id: "ThoJuroQueEsUnID",
					Time: &sessionsv1.NewResponseTime{
						MaxTime:        timestamppb.New(time.Now().Add(8 * time.Hour)),
						MaxRenewTime:   timestamppb.New(time.Now().Add(30 * time.Minute)),
						ExpirationTime: timestamppb.New(time.Now().Add(5 * time.Minute)),
					},
				})
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			RemoteAddr: "127.0.0.1",
			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "check if the user has notifications pending: notifications error",
		},
		"should return an error if the pending notifications check returns an unexpected response": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)

				m.On(r.Table("users").Get("user-1")).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)

				m.On(r.Table("users").Get("user-1").Update(r.MockAnything())).Return(r.WriteResponse{Updated: 1}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckMigrationRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckMigrationRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckEmailVerification", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckEmailVerificationParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminCheckPasswordResetRequired", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckPasswordResetRequiredParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: false}, nil)
				c.On("AdminGetUserNotificationDisplays", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminGetUserNotificationDisplaysParams{UserID: "user-1", Trigger: apiv4.NotificationTriggerEnumLogin}).Return(&apiv4.AdminGetUserNotificationDisplaysUnauthorized{}, nil)
			},
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/New").WithPayload(&sessionsv1.NewRequest{
					UserId:     "user-1",
					RemoteAddr: "127.0.0.1",
				}).Return(&sessionsv1.NewResponse{
					Id: "ThoJuroQueEsUnID",
					Time: &sessionsv1.NewResponseTime{
						MaxTime:        timestamppb.New(time.Now().Add(8 * time.Hour)),
						MaxRenewTime:   timestamppb.New(time.Now().Add(30 * time.Minute)),
						ExpirationTime: timestamppb.New(time.Now().Add(5 * time.Minute)),
					},
				})
			},
			PrepareProvider: func(p *provider.MockProvider) {
				p.On("SaveEmail").Return(true)
				p.On("String").Return("saml")
			},

			RemoteAddr: "127.0.0.1",
			Provider:   "saml",
			CategoryID: "default",
			ProviderUserData: func() *types.ProviderUserData {
				return &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}
			},
			Redirect: "/",

			ExpectedErr: "check if the user has notifications pending: unexpected response type *apiv4.AdminGetUserNotificationDisplaysUnauthorized",
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

			if tc.PrepareSessions != nil {
				sessionsMockServer := grpcmock.NewServer(
					grpcmock.RegisterService(sessionsv1.RegisterSessionsServiceServer),
					tc.PrepareSessions,
				)
				t.Cleanup(func() {
					sessionsMockServer.Close()
				})

				sessionsCli, sessionsConn, err := grpc.NewClient(ctx, sessionsv1.NewSessionsServiceClient, sessionsMockServer.Address())
				require.NoError(err)
				defer sessionsConn.Close()

				a.Sessions = sessionsCli
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

func TestCallback(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB              func(*r.Mock)
		PrepareAPI             func(*apiv4.MockInvoker)
		PrepareProviderManager func(*testing.T, *providermanager.MockProvidermanager)

		RemoteAddr   string
		PrepareToken func() string

		CheckToken       func(string)
		ExpectedRedirect string
		ExpectedErr      string
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]any{
					map[string]any{
						"id": "default",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				samlMock := provider.NewMockProvider(t)
				samlMock.On("Callback", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(claims *token.CallbackClaims) bool {
					return claims.Provider == "saml" && claims.CategoryID == "default" && claims.Redirect == "/from-callback"
				}), provider.CallbackArgs{}).Return((*model.Group)(nil), []*model.Group{}, &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				}, "", "", (*provider.ProviderError)(nil))
				samlMock.On("SaveEmail").Return(true)
				samlMock.On("String").Return("saml")

				m.On("Provider", "saml", "default").Return(samlMock)
			},
			RemoteAddr: "127.0.0.1",
			PrepareToken: func() string {
				ss, err := token.SignCallbackToken("", "saml", "default", "/from-callback")
				require.NoError(err)

				return ss
			},

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-1", tkn.UserID)
			},
			ExpectedRedirect: "/from-callback",
		},
		"should return the token signed by the provider": {
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				samlMock := provider.NewMockProvider(t)
				samlMock.On("Callback", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(claims *token.CallbackClaims) bool {
					return claims.Provider == "saml" && claims.CategoryID == "default" && claims.Redirect == "/from-callback"
				}), provider.CallbackArgs{}).Return((*model.Group)(nil), []*model.Group{}, (*types.ProviderUserData)(nil), "", "provider-token", (*provider.ProviderError)(nil))

				m.On("Provider", "saml", "default").Return(samlMock)
			},
			RemoteAddr: "127.0.0.1",
			PrepareToken: func() string {
				ss, err := token.SignCallbackToken("", "saml", "default", "/from-callback")
				require.NoError(err)

				return ss
			},

			CheckToken: func(ss string) {
				assert.Equal("provider-token", ss)
			},
			ExpectedRedirect: "/from-callback",
		},
		"should return an error if the callback token cannot be parsed": {
			RemoteAddr: "127.0.0.1",
			PrepareToken: func() string {
				return "invalid-token"
			},

			ExpectedErr: "parse callback state: error parsing the JWT token: token is malformed: token contains an invalid number of segments",
		},
		"should return an error if the provider callback fails": {
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				samlMock := provider.NewMockProvider(t)
				samlMock.On("Callback", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(claims *token.CallbackClaims) bool {
					return claims.Provider == "saml" && claims.CategoryID == "default"
				}), provider.CallbackArgs{}).Return((*model.Group)(nil), []*model.Group{}, (*types.ProviderUserData)(nil), "", "", &provider.ProviderError{
					User:   provider.ErrInvalidCredentials,
					Detail: errors.New("callback failed"),
				})
				samlMock.On("String").Return("saml")

				m.On("Provider", "saml", "default").Return(samlMock)
			},
			RemoteAddr: "127.0.0.1",
			PrepareToken: func() string {
				ss, err := token.SignCallbackToken("", "saml", "default", "/from-callback")
				require.NoError(err)

				return ss
			},

			ExpectedErr: "callback: invalid credentials: callback failed",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()

			log := log.New("authentication-test", "debug")

			dbMock := r.NewMock()
			if tc.PrepareDB != nil {
				tc.PrepareDB(dbMock)
			}

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

			tkn, redirect, err := a.Callback(ctx, tc.PrepareToken(), provider.CallbackArgs{}, tc.RemoteAddr)

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

func TestFinishRegister(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB  func(*r.Mock)
		PrepareAPI func(*apiv4.MockInvoker)

		PrepareToken func() string

		CheckToken       func(string)
		ExpectedRedirect string
		ExpectedErr      string
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"ldap",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareToken: func() string {
				ss, err := token.SignRegisterToken("", &model.User{
					Provider: "ldap",
					Category: "default",
					UID:      "nefix-uid",
				})
				require.NoError(err)

				return ss
			},

			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should return an error if the register token cannot be parsed": {
			PrepareToken: func() string {
				return "invalid-token"
			},

			ExpectedErr: "error parsing the JWT token: token is malformed: token contains an invalid number of segments",
		},
		"should return an error if the user is not registered": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"ldap",
				})).Return([]any{}, nil)
			},
			PrepareToken: func() string {
				ss, err := token.SignRegisterToken("", &model.User{
					Provider: "ldap",
					Category: "default",
					UID:      "nefix-uid",
				})
				require.NoError(err)

				return ss
			},

			ExpectedErr: "user not registered",
		},
		"should return an error if loading the user fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"ldap",
				})).Return(nil, fmt.Errorf("db error"))
			},
			PrepareToken: func() string {
				ss, err := token.SignRegisterToken("", &model.User{
					Provider: "ldap",
					Category: "default",
					UID:      "nefix-uid",
				})
				require.NoError(err)

				return ss
			},

			ExpectedErr: "load user from db: db error",
		},
		"should return an error if the login cannot be finished": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"ldap",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": false,
					},
				}, nil)
			},
			PrepareToken: func() string {
				ss, err := token.SignRegisterToken("", &model.User{
					Provider: "ldap",
					Category: "default",
					UID:      "nefix-uid",
				})
				require.NoError(err)

				return ss
			},

			ExpectedErr: provider.ErrUserDisabled.Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()

			log := log.New("authentication-test", "debug")

			dbMock := r.NewMock()
			if tc.PrepareDB != nil {
				tc.PrepareDB(dbMock)
			}

			apiMock := apiv4.NewMockInvoker(t)
			if tc.PrepareAPI != nil {
				tc.PrepareAPI(apiMock)
			}

			a := &Authentication{
				Log:    log,
				Secret: "",
				DB:     dbMock,
				API:    apiMock,
			}

			tkn, redirect, err := a.finishRegister(ctx, "127.0.0.1", tc.PrepareToken(), "/")

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
			if tc.ExpectedErr != "" {
				assert.Empty(redirect)
			} else {
				assert.Equal(tc.ExpectedRedirect, redirect)
			}

			dbMock.AssertExpectations(t)
			apiMock.AssertExpectations(t)
		})
	}
}

func TestFinishReRegister(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB              func(*r.Mock)
		PrepareAPI             func(*apiv4.MockInvoker)
		PrepareProviderManager func(*testing.T, *providermanager.MockProvidermanager)

		PrepareToken func() string

		CheckToken       func(string)
		ExpectedRedirect string
		ExpectedErr      string
	}{
		"should complete the login when the applied code lifts the restriction": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
						"role":   "manager",
					},
				}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCheckDisclaimer", mock.AnythingOfType("context.backgroundCtx"), apiv4.AdminCheckDisclaimerParams{UserID: "user-1"}).Return(&apiv4.RequiredCheckResponse{Required: true}, nil)
			},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				p := provider.NewMockProvider(t)
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleManager
				})).Return(false)
				m.On("Provider", "saml", "default").Return(p)
			},
			PrepareToken: func() string {
				ss, err := token.SignReRegisterToken("", &model.User{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
					Role:     model.RoleManager,
				})
				require.NoError(err)

				return ss
			},
			CheckToken: func(ss string) {
				tkn, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				require.NoError(err)

				assert.Equal("user-1", tkn.UserID)
			},
			ExpectedRedirect: "/",
		},
		"should re-issue a re-register token when the code did not lift the restriction": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
						"role":   "user",
					},
				}, nil)
			},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				p := provider.NewMockProvider(t)
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleManager
				})).Return(false)
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleUser
				})).Return(true)
				m.On("Provider", "saml", "default").Return(p)
			},
			PrepareToken: func() string {
				ss, err := token.SignReRegisterToken("", &model.User{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
					Role:     model.RoleManager,
				})
				require.NoError(err)

				return ss
			},
			CheckToken: func(ss string) {
				tkn, err := token.ParseReRegisterToken("", ss)
				require.NoError(err)

				assert.Equal("saml", tkn.Provider)
				assert.Equal("nefix-uid", tkn.UserID)
				assert.Equal("default", tkn.CategoryID)
				assert.Equal("manager", tkn.RoleID)
			},
			ExpectedRedirect: "/",
		},
		"should re-issue a re-register token when the guessed role is empty and the stored role is still in the list": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{
					map[string]any{
						"id":     "user-1",
						"active": true,
						"role":   "user",
					},
				}, nil)
			},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				p := provider.NewMockProvider(t)
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == ""
				})).Return(false)
				p.On("AutoRegister", mock.MatchedBy(func(u *model.User) bool {
					return u.Role == model.RoleUser
				})).Return(true)
				m.On("Provider", "saml", "default").Return(p)
			},
			PrepareToken: func() string {
				ss, err := token.SignReRegisterToken("", &model.User{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				})
				require.NoError(err)

				return ss
			},
			CheckToken: func(ss string) {
				tkn, err := token.ParseReRegisterToken("", ss)
				require.NoError(err)

				assert.Equal("saml", tkn.Provider)
				assert.Equal("nefix-uid", tkn.UserID)
				assert.Equal("default", tkn.CategoryID)
				assert.Equal("", tkn.RoleID)
			},
			ExpectedRedirect: "/",
		},
		"should return an error if the re-register token cannot be parsed": {
			PrepareToken: func() string {
				return "invalid-token"
			},

			ExpectedErr: "error parsing the JWT token: token is malformed: token contains an invalid number of segments",
		},
		"should return an error if the user is not registered": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return([]any{}, nil)
			},
			PrepareToken: func() string {
				ss, err := token.SignReRegisterToken("", &model.User{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
					Role:     model.RoleManager,
				})
				require.NoError(err)

				return ss
			},

			ExpectedErr: "user not registered",
		},
		"should return an error if loading the user fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"nefix-uid",
					"default",
					"saml",
				})).Return(nil, fmt.Errorf("db error"))
			},
			PrepareToken: func() string {
				ss, err := token.SignReRegisterToken("", &model.User{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
					Role:     model.RoleManager,
				})
				require.NoError(err)

				return ss
			},

			ExpectedErr: "load user from db: db error",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()

			log := log.New("authentication-test", "debug")

			dbMock := r.NewMock()
			if tc.PrepareDB != nil {
				tc.PrepareDB(dbMock)
			}

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
				DB:         dbMock,
				API:        apiMock,
				prvManager: prvManagerMock,
			}

			tkn, redirect, err := a.finishReRegister(ctx, "127.0.0.1", tc.PrepareToken(), "/")

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
			if tc.ExpectedErr != "" {
				assert.Empty(redirect)
			} else {
				assert.Equal(tc.ExpectedRedirect, redirect)
			}

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
				localMock.On("String").Return("local")

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
				samlMock.On("String").Return("saml")

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
				localMock.On("String").Return("local")

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
		"should return an error if guessing the groups fails": {
			PrepareDB:  func(m *r.Mock) {},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			PrepareProviderManager: func(t *testing.T, m *providermanager.MockProvidermanager) {
				username := "saml-uid"
				name := "SAML User"

				samlMock := provider.NewMockProvider(t)
				samlMock.On("GuessGroups", mock.AnythingOfType("*context.cancelCtx"), &types.ProviderUserData{
					Provider: "saml",
					Category: "test-category",
					UID:      "saml-uid",
					Username: &username,
					Name:     &name,
				}, []string{"group1"}).Return((*model.Group)(nil), []*model.Group{}, &provider.ProviderError{
					User:   provider.ErrInternal,
					Detail: errors.New("guess error"),
				})

				m.On("Provider", "saml", "test-category").Return(samlMock)
			},
			RemoteAddr: "127.0.0.1",
			CategoryID: "test-category",
			PrepareToken: func() string {
				username := "saml-uid"
				name := "SAML User"

				tkn, err := token.SignCategorySelectToken("", []*model.Category{{
					ID:   "test-category",
					Name: "Test Category",
				}}, &[]string{"group1"}, nil, &types.ProviderUserData{
					Provider: "saml",
					Category: "default",
					UID:      "saml-uid",

					Username: &username,
					Name:     &name,
				})
				require.NoError(err)
				return tkn
			},
			Redirect: "/",

			ExpectedErr: "guess groups from token: internal server error: guess error",
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
