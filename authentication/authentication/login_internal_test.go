package authentication

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"gitlab.com/isard/isardvdi/pkg/sdk"
	"go.nhat.io/grpcmock"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestStartLogin(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB       func(*r.Mock)
		PrepareAPI      func(*sdk.MockSdk)
		PrepareProvider func(*provider.MockProvider)
		PrepareSessions func(*grpcmock.Server)

		RemoteAddr       string
		Provider         string
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
								"enabled":         true,
								"allowed_domains": []string{"example.org"},
							},
						},
					},
				}, nil)
			},
			PrepareAPI:      func(c *sdk.MockSdk) {},
			PrepareSessions: func(s *grpcmock.Server) {},

			Provider: "local",
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
								"enabled":         true,
								"allowed_domains": []string{"example.org"},
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
			Provider: "mock",
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
			PrepareAPI:      func(c *sdk.MockSdk) {},
			PrepareSessions: func(s *grpcmock.Server) {},

			Provider: "local",
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
								"enabled":         true,
								"allowed_domains": []string{},
							},
						},
					},
				}, nil)
			},
			PrepareAPI:      func(s *sdk.MockSdk) {},
			PrepareSessions: func(s *grpcmock.Server) {},

			Provider: "local",
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
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()

			cfg := cfg.New()
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

			if tc.PrepareSessions == nil {
				tc.PrepareSessions = func(s *grpcmock.Server) {}
			}
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

			a := Init(cfg, log, dbMock, nil, nil, sessionsCli)
			a.API = apiMock
			a.providers["mock"] = providerMock

			p := a.Provider(tc.Provider)

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
		PrepareDB             func(*r.Mock)
		PrepareAPI            func(*sdk.MockSdk)
		PrepareSessions       func(*grpcmock.Server)
		PrepareAuthentication func(*testing.T, *Authentication)

		RemoteAddr   string
		CategoryID   string
		PrepareToken func() string
		Redirect     string

		CheckToken       func(string)
		ExpectedRedirect string
		ExpectedErr      string
	}{
		"should handle the errors correctly": {
			PrepareDB:       func(m *r.Mock) {},
			PrepareAPI:      func(c *sdk.MockSdk) {},
			PrepareSessions: func(s *grpcmock.Server) {},
			PrepareAuthentication: func(t *testing.T, a *Authentication) {
				uid := "90c658f3-0c9b-41b7-9710-44c98f74630f"
				name := "Néfix Estrada Campañá"
				empty := ""

				samlMock := provider.NewMockProvider(t)
				samlMock.On("GuessRole", mock.AnythingOfType("context.backgroundCtx"), &types.ProviderUserData{
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

				a.providers["saml"] = samlMock
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
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			assert := assert.New(t)

			ctx := context.Background()

			cfg := cfg.New()
			log := log.New("authentication-test", "debug")

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			apiMock := sdk.NewMockSdk(t)
			if tc.PrepareAPI != nil {
				tc.PrepareAPI(apiMock)
			}

			if tc.PrepareSessions == nil {
				tc.PrepareSessions = func(s *grpcmock.Server) {}
			}
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

			a := Init(cfg, log, dbMock, nil, nil, sessionsCli)
			a.API = apiMock

			if tc.PrepareAuthentication != nil {
				tc.PrepareAuthentication(t, a)
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
