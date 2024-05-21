package authentication_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/pkg/gen/oas/notifier"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestRequestEmailVerification(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)
	now := float64(time.Now().Unix())

	cases := map[string]struct {
		PrepareDB       func(*r.Mock)
		PrepareToken    func() string
		PrepareNotifier func(*notifier.MockInvoker)
		Email           string
		ExpectedErr     string
	}{
		"should work as expected": {
			PrepareToken: func() string {
				tkn, err := token.SignEmailVerificationRequiredToken("", &model.User{
					ID:       "néfix néfix imagine this is an UUID",
					Category: "default",
				})
				require.NoError(err)

				return tkn
			},
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("category"), "default"),
					r.Eq(r.Row.Field("email"), "nefix@example.org"),
					r.Ne(r.Row.Field("email_verified"), nil),
				))).Return([]interface{}{}, nil)
				m.On(r.Table("users").Get("néfix néfix imagine this is an UUID").Update(map[string]interface{}{
					"email":                    "nefix@example.org",
					"email_verified":           r.MockAnything(),
					"email_verification_token": r.MockAnything(),
				})).Return(r.WriteResponse{
					Updated: 1,
				}, nil)
			},
			PrepareNotifier: func(c *notifier.MockInvoker) {
				c.On("PostNotifierMailEmailVerify", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req notifier.OptNotifyEmailVerifyMailRequest0bf6af6) bool {
					return req.Set &&
						req.Value.Email == "nefix@example.org" &&
						strings.HasPrefix(req.Value.URL, "https://localhost/verify-email?token=e")
				})).Return(&notifier.NotifyEmailVerifyMailResponse0bf6af6{
					TaskID: uuid.New(),
				}, nil)
			},
			Email: "nefix@example.org",
		},
		"should return an error if the token is invalid": {
			PrepareToken: func() string {
				tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &token.EmailVerificationRequiredClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							ExpiresAt: jwt.NewNumericDate(time.Now().Add(-60 * time.Minute)), // This token is expired!
							IssuedAt:  jwt.NewNumericDate(time.Now()),
							NotBefore: jwt.NewNumericDate(time.Now()),
							Issuer:    "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeEmailVerificationRequired,
					},
					UserID: "néfix néfix imagine this is an UUID",
				})

				ss, err := tkn.SignedString([]byte(""))
				require.NoError(err)

				return ss
			},
			ExpectedErr: "error parsing the JWT token: token has invalid claims: token is expired",
		},
		"should return an error if the token isn't of type email-verification-required": {
			PrepareToken: func() string {
				tkn, err := token.SignCallbackToken("", "local", "default", "")
				require.NoError(err)

				return tkn
			},
			ExpectedErr: "error parsing the JWT token: token has invalid claims: invalid token type",
		},
		"should return an error if the email is invalid": {
			PrepareToken: func() string {
				tkn, err := token.SignEmailVerificationRequiredToken("", &model.User{
					ID: "néfix néfix imagine this is an UUID",
				})
				require.NoError(err)

				return tkn
			},
			Email:       "invalid email! :D",
			ExpectedErr: "invalid email",
		},
		"should return an error if the email already exists": {
			PrepareToken: func() string {
				tkn, err := token.SignEmailVerificationRequiredToken("", &model.User{
					ID:       "néfix néfix imagine this is an UUID",
					Category: "default",
				})
				require.NoError(err)

				return tkn
			},
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("category"), "default"),
					r.Eq(r.Row.Field("email"), "nefix@example.org"),
					r.Ne(r.Row.Field("email_verified"), nil),
				))).Return([]interface{}{
					map[string]interface{}{
						"id":             "local-default-admin-admin",
						"uid":            "admin",
						"username":       "admin",
						"password":       "f0ckt3Rf$",
						"provider":       "local",
						"category":       "default",
						"role":           "default",
						"group":          "default",
						"name":           "Administrator",
						"email":          "nefix@example.org",
						"email_verified": &now,
						"photo":          "https://isardvdi.com/path/to/photo.jpg",
					},
				}, nil)
			},
			Email:       "nefix@example.org",
			ExpectedErr: "email address already in use",
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

			a := authentication.Init(cfg, log, mock, nil, nil, nil)

			if tc.PrepareNotifier != nil {
				tc.PrepareNotifier(notifier)
			}
			a.Notifier = notifier

			err := a.RequestEmailVerification(context.Background(), tc.PrepareToken(), tc.Email)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			mock.AssertExpectations(t)
		})
	}
}

func TestVerifyEmail(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareDB    func(*r.Mock)
		PrepareToken func() string
		ExpectedErr  string
	}{
		"should work as expected": {
			PrepareToken: func() string {
				tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &token.EmailVerificationClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeEmailVerification,
					},
					UserID: "néfix néfix imagine this is an UUID",
					Email:  "nefix@example.org",
				})

				ss, err := tkn.SignedString([]byte(""))
				require.NoError(err)

				return ss
			},
			PrepareDB: func(m *r.Mock) {
				tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &token.EmailVerificationClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeEmailVerification,
					},
					UserID: "néfix néfix imagine this is an UUID",
					Email:  "nefix@example.org",
				})

				ss, err := tkn.SignedString([]byte(""))
				require.NoError(err)

				m.On(r.Table("users").Get("néfix néfix imagine this is an UUID")).Return([]interface{}{
					map[string]interface{}{
						"id":                       "néfix néfix imagine this is an UUID",
						"email_verification_token": ss,
					},
				}, nil)
				m.On(r.Table("users").Get("néfix néfix imagine this is an UUID").Update(map[string]interface{}{
					"email":                    "nefix@example.org",
					"email_verified":           r.MockAnything(),
					"email_verification_token": "",
				})).Return(r.WriteResponse{
					Updated: 1,
				}, nil)
			},
		},
		"should return an error if the token is invalid": {
			PrepareToken: func() string {
				tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &token.EmailVerificationClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							ExpiresAt: jwt.NewNumericDate(time.Now().Add(-60 * time.Minute)), // This token is expired!
							IssuedAt:  jwt.NewNumericDate(time.Now()),
							NotBefore: jwt.NewNumericDate(time.Now()),
							Issuer:    "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeEmailVerification,
					},
					UserID: "néfix néfix imagine this is an UUID",
					Email:  "nefix@example.org",
				})

				ss, err := tkn.SignedString([]byte(""))
				require.NoError(err)

				return ss
			},
			ExpectedErr: "error parsing the JWT token: token has invalid claims: token is expired",
		},
		"should return an error if the token isn't of type email-verification": {
			PrepareToken: func() string {
				ss, err := token.SignCallbackToken("", "local", "default", "")
				require.NoError(err)

				return ss
			},
			ExpectedErr: "error parsing the JWT token: token has invalid claims: invalid token type",
		},
		"should return an error if there's an error loading the user from the DB": {
			PrepareToken: func() string {
				ss, err := token.SignEmailVerificationToken("", "néfix néfix imagine this is an UUID", "nefix@example.org")
				require.NoError(err)

				return ss
			},
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("néfix néfix imagine this is an UUID")).Return(nil, errors.New("hello! :D"))
			},
			ExpectedErr: "load the user from the DB: hello! :D",
		},
		"should return an error if the token stored in the DB is different than the one provided": {
			PrepareToken: func() string {
				ss, err := token.SignEmailVerificationToken("", "néfix néfix imagine this is an UUID", "nefix@example.org")
				require.NoError(err)

				return ss
			},
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("néfix néfix imagine this is an UUID")).Return([]interface{}{
					map[string]interface{}{
						"id":                       "néfix néfix imagine this is an UUID",
						"email_verification_token": "another different token! :O",
					},
				}, nil)
			},
			ExpectedErr: "token mismatch",
		},
		"should return an error if there's an error updating the DB": {
			PrepareToken: func() string {
				tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &token.EmailVerificationClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeEmailVerification,
					},
					UserID: "néfix néfix imagine this is an UUID",
					Email:  "nefix@example.org",
				})

				ss, err := tkn.SignedString([]byte(""))
				require.NoError(err)

				return ss
			},
			PrepareDB: func(m *r.Mock) {
				tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &token.EmailVerificationClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeEmailVerification,
					},
					UserID: "néfix néfix imagine this is an UUID",
					Email:  "nefix@example.org",
				})

				ss, err := tkn.SignedString([]byte(""))
				require.NoError(err)

				m.On(r.Table("users").Get("néfix néfix imagine this is an UUID")).Return([]interface{}{
					map[string]interface{}{
						"id":                       "néfix néfix imagine this is an UUID",
						"email_verification_token": ss,
					},
				}, nil)
				m.On(r.Table("users").Get("néfix néfix imagine this is an UUID").Update(map[string]interface{}{
					"email":                    "nefix@example.org",
					"email_verified":           r.MockAnything(),
					"email_verification_token": "",
				})).Return(nil, errors.New("hello reader! :D"))
			},
			ExpectedErr: "update the DB: hello reader! :D",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			cfg := cfg.New()
			log := log.New("authentication-test", "debug")
			mock := r.NewMock()

			if tc.PrepareDB != nil {
				tc.PrepareDB(mock)
			}

			a := authentication.Init(cfg, log, mock, nil, nil, nil)

			err := a.VerifyEmail(context.Background(), tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			mock.AssertExpectations(t)
		})
	}
}
