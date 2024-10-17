package authentication

import (
	"context"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/log"

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
