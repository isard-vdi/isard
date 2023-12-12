package authentication_test

import (
	"context"
	"strings"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi-sdk-go"
	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/pkg/gen/oas/notifier"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	apiMock "gitlab.com/isard/isardvdi-sdk-go/mock"
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
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("category"), "default"),
					r.Eq(r.Row.Field("email"), "nefix@example.org"),
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
				c.On("PostNotifierMailPasswordReset", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req notifier.OptNotifyPasswordResetMailRequest0bf6af6) bool {
					return req.Set &&
						req.Value.Email == "nefix@example.org" &&
						strings.HasPrefix(req.Value.URL, "https://localhost/reset-password?token=e")

				})).Return(&notifier.NotifyPasswordResetMailResponse0bf6af6{
					TaskID: uuid.New(),
				}, nil)
			},
			CategoryID: "default",
			Email:      "nefix@example.org",
		},
		"should return an error if the user isn't found": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("category"), "default"),
					r.Eq(r.Row.Field("email"), "nefix@example.org"),
				))).Return([]interface{}{}, nil)
			},
			CategoryID:  "default",
			Email:       "nefix@example.org",
			ExpectedErr: "user not found",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			cfg := cfg.New()
			log := log.New("authentication-test", "debug")
			mock := r.NewMock()
			notifier := notifier.NewMockInvoker(t)

			if tc.PrepareDB != nil {
				tc.PrepareDB(mock)
			}

			a := authentication.Init(cfg, log, mock)

			if tc.PrepareNotifier != nil {
				tc.PrepareNotifier(notifier)
			}
			a.Notifier = notifier

			err := a.ForgotPassword(context.Background(), tc.CategoryID, tc.Email)

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
		PrepareAPI   func(*apiMock.Client)
		PrepareToken func() string
		Password     string
		ExpectedErr  string
	}{
		"should work as expected with a login token": {
			PrepareAPI: func(c *apiMock.Client) {
				c.On("AdminUserResetPassword", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654", "f0kt3Rf").Return(nil)
			},
			PrepareToken: func() string {
				ss, err := token.SignLoginToken("", time.Hour, &model.User{
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
					EmailVerified:          true,
					DisclaimerAcknowledged: true,
				})
				require.NoError(err)

				return ss
			},
			Password: "f0kt3Rf",
		},
		"should work as expected with a password reset token": {
			PrepareAPI: func(c *apiMock.Client) {
				c.On("AdminUserResetPassword", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654", "f0kt3Rf").Return(nil)
			},
			PrepareToken: func() string {
				ss, err := token.SignPasswordResetToken("", "08fff46e-cbd3-40d2-9d8e-e2de7a8da654")
				require.NoError(err)

				return ss
			},
			Password: "f0kt3Rf",
		},
		"should return an API error if there's an error calling the API": {
			PrepareAPI: func(c *apiMock.Client) {
				err := isardvdi.ErrBadRequest
				err.Description = "Password must have at least 1 special characters: !@#$%^&*()-_=+[]{}|;:'\",.<>/?"
				err.DescriptionCode = "password_special_characters"

				c.On("AdminUserResetPassword", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654", "weak password :3").Return(err)
			},
			PrepareToken: func() string {
				ss, err := token.SignPasswordResetToken("", "08fff46e-cbd3-40d2-9d8e-e2de7a8da654")
				require.NoError(err)

				return ss
			},
			Password:    "weak password :3",
			ExpectedErr: "http status code 400: bad_request: Bad request: password_special_characters: Password must have at least 1 special characters: !@#$%^&*()-_=+[]{}|;:'\",.<>/?",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			cfg := cfg.New()
			log := log.New("authentication-test", "debug")
			apiMock := &apiMock.Client{}

			if tc.PrepareAPI != nil {
				tc.PrepareAPI(apiMock)
			}

			a := authentication.Init(cfg, log, nil)
			a.Client = apiMock

			err := a.ResetPassword(context.Background(), tc.PrepareToken(), tc.Password)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			apiMock.AssertExpectations(t)
		})
	}
}
