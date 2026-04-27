package authentication_test

import (
	"context"
	"strings"
	"sync"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/gen/oas/notifier"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"go.nhat.io/grpcmock"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestForgotPassword(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB       func(*r.Mock)
		PrepareNotifier func(*notifier.MockInvoker)
		CategoryID      string
		Email           string
		ExpectedErr     string
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]interface{}{}, nil)
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("category"), "default"),
					r.Eq(r.Row.Field("email"), "nefix@example.org"),
					r.Ne(r.Row.Field("email_verified"), nil),
				))).Return([]interface{}{
					map[string]interface{}{
						"id":    "néfix imagine this is an UUID",
						"email": "nefix@example.org",
					},
				}, nil)
				m.On(r.Table("users").Get("néfix imagine this is an UUID").Update(map[string]interface{}{
					"password_reset_token": r.MockAnything(),
				})).Return(r.WriteResponse{
					Updated: 1,
				}, nil)
			},
			PrepareNotifier: func(c *notifier.MockInvoker) {
				c.On("PostNotifierMailPasswordReset", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req *notifier.NotifyPasswordResetMailRequest0bf6af6) bool {
					return req.Email == "nefix@example.org" &&
						strings.HasPrefix(req.URL, "https://localhost/reset-password?token=e")

				})).Return(&notifier.NotifyPasswordResetMailResponse0bf6af6{
					TaskID: uuid.New(),
				}, nil)
			},
			CategoryID: "default",
			Email:      "nefix@example.org",
		},
		"should return an error if the user isn't found": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]interface{}{}, nil)
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("category"), "default"),
					r.Eq(r.Row.Field("email"), "nefix@example.org"),
					r.Ne(r.Row.Field("email_verified"), nil),
				))).Return([]interface{}{}, nil)
			},
			CategoryID:  "default",
			Email:       "nefix@example.org",
			ExpectedErr: "user not found",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			var wg sync.WaitGroup
			defer wg.Wait()
			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()

			cfg := cfg.New()
			log := log.New("authentication-test", "debug")
			mock := r.NewMock()
			notifier := notifier.NewMockInvoker(t)

			if tc.PrepareDB != nil {
				tc.PrepareDB(mock)
			}

			a := authentication.Init(ctx, &wg, cfg, log, mock, nil, nil, nil)

			if tc.PrepareNotifier != nil {
				tc.PrepareNotifier(notifier)
			}
			a.Notifier = notifier

			err := a.ForgotPassword(t.Context(), tc.CategoryID, tc.Email)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			mock.AssertExpectations(t)
		})
	}
}

func TestResetPassword(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareAPI      func(*apiv4.MockInvoker)
		PrepareDB       func(*r.Mock)
		PrepareSessions func(*grpcmock.Server)
		PrepareToken    func() string
		Password        string
		RemoteAddr      string
		ExpectedErr     string
	}{
		"should work as expected with a login token": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminResetPassword", mock.AnythingOfType("*context.cancelCtx"), &apiv4.AdminPasswordResetData{UserID: "08fff46e-cbd3-40d2-9d8e-e2de7a8da654", Password: "f0kt3Rf"}).Return(&apiv4.EmptyResponse{}, nil)
			},
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]interface{}{}, nil)
				m.On(r.Table("users").Get("08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Update(map[string]interface{}{
					"password_reset_token": "",
				})).Return(r.WriteResponse{
					Updated: 1,
				}, nil)
			},
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/Get").WithPayload(&sessionsv1.GetRequest{
					Id:         "ThoJuroQueEsUnID",
					RemoteAddr: "127.0.0.1",
				}).Return(&sessionsv1.GetResponse{})
			},
			PrepareToken: func() string {
				now := float64(time.Now().Unix())

				ss, err := token.SignLoginToken("", time.Now().Add(time.Hour), "ThoJuroQueEsUnID", &model.User{
					ID:                     "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					UID:                    "nefix",
					Username:               "nefix",
					Password:               "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
					Provider:               "local",
					Active:                 true,
					Category:               "default",
					Role:                   "user",
					Group:                  "default-default",
					Name:                   "Néfix Estrada",
					Email:                  "nefix@example.org",
					EmailVerified:          &now,
					DisclaimerAcknowledged: true,
				})
				require.NoError(err)

				return ss
			},
			Password:   "f0kt3Rf",
			RemoteAddr: "127.0.0.1",
		},
		"should work as expected with a password reset token": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminResetPassword", mock.AnythingOfType("*context.cancelCtx"), &apiv4.AdminPasswordResetData{UserID: "08fff46e-cbd3-40d2-9d8e-e2de7a8da654", Password: "f0kt3Rf"}).Return(&apiv4.EmptyResponse{}, nil)
			},
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]interface{}{}, nil)
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("id"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654"),
					r.Eq(r.Row.Field("password_reset_token"), r.MockAnything()),
				))).Return(map[string]interface{}{
					"id": "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
				}, nil)
				m.On(r.Table("users").Get("08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Update(map[string]interface{}{
					"password_reset_token": "",
				})).Return(r.WriteResponse{
					Updated: 1,
				}, nil)
			},
			PrepareToken: func() string {
				ss, err := token.SignPasswordResetToken("", "08fff46e-cbd3-40d2-9d8e-e2de7a8da654")
				require.NoError(err)

				return ss
			},
			Password: "f0kt3Rf",
		},
		"should return an API error if there's an error calling the API": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminResetPassword", mock.AnythingOfType("*context.cancelCtx"), &apiv4.AdminPasswordResetData{UserID: "08fff46e-cbd3-40d2-9d8e-e2de7a8da654", Password: "weak password :3"}).Return(&apiv4.ErrorResponse{
					Error:           "bad_request",
					Msg:             "Bad request",
					DescriptionCode: "password_special_characters",
					Description:     "Password must have at least 1 special characters: !@#$%^&*()-_=+[]{}|;:'\",.<>/?",
				}, nil)
			},
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]interface{}{}, nil)
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("id"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654"),
					r.Eq(r.Row.Field("password_reset_token"), r.MockAnything()),
				))).Return(map[string]interface{}{
					"id": "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
				}, nil)
			},
			PrepareToken: func() string {
				ss, err := token.SignPasswordResetToken("", "08fff46e-cbd3-40d2-9d8e-e2de7a8da654")
				require.NoError(err)

				return ss
			},
			Password:    "weak password :3",
			ExpectedErr: "ogen 500 bad_request: Password must have at least 1 special characters: !@#$%^&*()-_=+[]{}|;:'\",.<>/? [password_special_characters]",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			var wg sync.WaitGroup
			defer wg.Wait()
			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()

			cfg := cfg.New()
			log := log.New("authentication-test", "debug")
			apiMock := apiv4.NewMockInvoker(t)
			dbMock := r.NewMock()

			if tc.PrepareAPI != nil {
				tc.PrepareAPI(apiMock)
			}

			if tc.PrepareDB != nil {
				tc.PrepareDB(dbMock)
			}

			if tc.PrepareSessions == nil {
				tc.PrepareSessions = func(s *grpcmock.Server) {}
			}
			sessionsSrv := grpcmock.NewServer(
				grpcmock.RegisterService(sessionsv1.RegisterSessionsServiceServer),
				tc.PrepareSessions,
			)
			t.Cleanup(func() {
				sessionsSrv.Close()
			})

			sessionsCli, sessionsConn, err := grpc.NewClient(ctx, sessionsv1.NewSessionsServiceClient, sessionsSrv.Address())
			require.NoError(err)
			defer sessionsConn.Close()

			a := authentication.Init(ctx, &wg, cfg, log, dbMock, nil, nil, sessionsCli)
			a.API = apiMock

			err = a.ResetPassword(t.Context(), tc.PrepareToken(), tc.Password, tc.RemoteAddr)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			apiMock.AssertExpectations(t)
		})
	}
}
