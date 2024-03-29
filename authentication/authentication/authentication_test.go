package authentication_test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	apiMock "gitlab.com/isard/isardvdi-sdk-go/mock"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestLogin(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)
	now := float64(time.Now().Unix())

	cases := map[string]struct {
		PrepareDB  func(*r.Mock)
		PrepareAPI func(*apiMock.Client)

		Provider    string
		CategoryID  string
		PrepareArgs func() map[string]string

		CheckToken       func(string)
		ExpectedRedirect string
		ExpectedErr      string
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{
					map[string]interface{}{
						"id":                      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":                     "nefix",
						"username":                "nefix",
						"password":                "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
						"password_reset_token":    "",
						"provider":                "local",
						"active":                  true,
						"category":                "default",
						"role":                    "user",
						"group":                   "default-default",
						"name":                    "Néfix Estrada",
						"email":                   "nefix@example.org",
						"email_verified":          &now,
						"disclaimer_acknowledged": true,
					},
				}, nil)
				m.On(r.Table("users").Get("08fff46e-cbd3-40d2-9d8e-e2de7a8da654")).Return([]interface{}{
					map[string]interface{}{
						"id":                      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":                     "nefix",
						"username":                "nefix",
						"password":                "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
						"password_reset_token":    "",
						"provider":                "local",
						"active":                  true,
						"category":                "default",
						"role":                    "user",
						"group":                   "default-default",
						"name":                    "Néfix Estrada",
						"email":                   "nefix@example.org",
						"email_verified":          &now,
						"disclaimer_acknowledged": true,
					},
				}, nil)
				m.On(r.Table("users").Get("08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Update(map[string]interface{}{
					"id":                       "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					"uid":                      "nefix",
					"username":                 "nefix",
					"password":                 "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
					"password_reset_token":     "",
					"provider":                 "local",
					"active":                   true,
					"category":                 "default",
					"role":                     "user",
					"group":                    "default-default",
					"name":                     "Néfix Estrada",
					"email":                    "nefix@example.org",
					"email_verified":           r.MockAnything(),
					"email_verification_token": "",
					"photo":                    "",
					"accessed":                 r.MockAnything(),
					"disclaimer_acknowledged":  true,
				})).Return(r.WriteResponse{
					Updated: 1,
				}, nil)
			},
			PrepareAPI: func(c *apiMock.Client) {
				c.On("AdminUserRequiredDisclaimerAcknowledgement", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
				c.On("AdminUserRequiredEmailVerification", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
				c.On("AdminUserRequiredPasswordReset", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() map[string]string {
				return map[string]string{
					"username": "nefix",
					"password": "f0kt3Rf$",
				}
			},
			CheckToken: func(ss string) {
				claims, err := token.ParseLoginToken("", ss)
				assert.NoError(err)

				assert.Equal("isard-authentication", claims.Issuer)
				assert.Equal("isardvdi", claims.KeyID)
				// TODO: Test time
				assert.Equal(token.LoginClaimsData{
					Provider:   "local",
					ID:         "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					RoleID:     "user",
					CategoryID: "default",
					GroupID:    "default-default",
					Name:       "Néfix Estrada",
				}, claims.Data)
			},
			ExpectedRedirect: "",
		},
		"should finish the login flow if the user provides a disclaimer-acknowledgement-required token": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("08fff46e-cbd3-40d2-9d8e-e2de7a8da654")).Return([]interface{}{
					map[string]interface{}{
						"id":                      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":                     "nefix",
						"username":                "nefix",
						"password":                "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
						"password_reset_token":    "",
						"provider":                "local",
						"active":                  true,
						"category":                "default",
						"role":                    "user",
						"group":                   "default-default",
						"name":                    "Néfix Estrada",
						"email":                   "nefix@example.org",
						"email_verified":          &now,
						"disclaimer_acknowledged": true,
					},
				}, nil)
				m.On(r.Table("users").Get("08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Update(map[string]interface{}{
					"id":                       "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					"uid":                      "nefix",
					"username":                 "nefix",
					"password":                 "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
					"password_reset_token":     "",
					"provider":                 "local",
					"active":                   true,
					"category":                 "default",
					"role":                     "user",
					"group":                    "default-default",
					"name":                     "Néfix Estrada",
					"email":                    "nefix@example.org",
					"email_verified":           r.MockAnything(),
					"email_verification_token": "",
					"photo":                    "",
					"disclaimer_acknowledged":  true,
					"accessed":                 r.MockAnything(),
				})).Return(r.WriteResponse{
					Updated: 1,
				}, nil)
			},
			PrepareAPI: func(c *apiMock.Client) {
				c.On("AdminUserRequiredDisclaimerAcknowledgement", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
				c.On("AdminUserRequiredEmailVerification", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
				c.On("AdminUserRequiredPasswordReset", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() map[string]string {
				ss, err := token.SignDisclaimerAcknowledgementRequiredToken("", "08fff46e-cbd3-40d2-9d8e-e2de7a8da654")
				require.NoError(err)

				return map[string]string{
					provider.TokenArgsKey: ss,
				}
			},
			CheckToken: func(ss string) {
				claims, err := token.ParseLoginToken("", ss)
				assert.NoError(err)

				assert.Equal("isard-authentication", claims.Issuer)
				assert.Equal("isardvdi", claims.KeyID)
				// TODO: Test time
				assert.Equal(token.LoginClaimsData{
					Provider:   "local",
					ID:         "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					RoleID:     "user",
					CategoryID: "default",
					GroupID:    "default-default",
					Name:       "Néfix Estrada",
				}, claims.Data)
			},
			ExpectedRedirect: "",
		},
		"should finish the login flow if the user provides a password-reset-required token": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("08fff46e-cbd3-40d2-9d8e-e2de7a8da654")).Return([]interface{}{
					map[string]interface{}{
						"id":                      "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":                     "nefix",
						"username":                "nefix",
						"password":                "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
						"password_reset_token":    "",
						"provider":                "local",
						"active":                  true,
						"category":                "default",
						"role":                    "user",
						"group":                   "default-default",
						"name":                    "Néfix Estrada",
						"email":                   "nefix@example.org",
						"email_verified":          &now,
						"disclaimer_acknowledged": true,
					},
				}, nil)
				m.On(r.Table("users").Get("08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Update(map[string]interface{}{
					"id":                       "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					"uid":                      "nefix",
					"username":                 "nefix",
					"password":                 "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
					"password_reset_token":     "",
					"provider":                 "local",
					"active":                   true,
					"category":                 "default",
					"role":                     "user",
					"group":                    "default-default",
					"name":                     "Néfix Estrada",
					"email":                    "nefix@example.org",
					"email_verified":           r.MockAnything(),
					"email_verification_token": "",
					"photo":                    "",
					"disclaimer_acknowledged":  true,
					"accessed":                 r.MockAnything(),
				})).Return(r.WriteResponse{
					Updated: 1,
				}, nil)
			},
			PrepareAPI: func(c *apiMock.Client) {
				c.On("AdminUserRequiredDisclaimerAcknowledgement", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
				c.On("AdminUserRequiredEmailVerification", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
				c.On("AdminUserRequiredPasswordReset", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() map[string]string {
				ss, err := token.SignPasswordResetRequiredToken("", "08fff46e-cbd3-40d2-9d8e-e2de7a8da654")
				require.NoError(err)

				return map[string]string{
					provider.TokenArgsKey: ss,
				}
			},
			CheckToken: func(ss string) {
				claims, err := token.ParseLoginToken("", ss)
				assert.NoError(err)

				assert.Equal("isard-authentication", claims.Issuer)
				assert.Equal("isardvdi", claims.KeyID)
				// TODO: Test time
				assert.Equal(token.LoginClaimsData{
					Provider:   "local",
					ID:         "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					RoleID:     "user",
					CategoryID: "default",
					GroupID:    "default-default",
					Name:       "Néfix Estrada",
				}, claims.Data)
			},
			ExpectedRedirect: "",
		},
		"should return an error if the user doesn't exist": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{}, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() map[string]string {
				return map[string]string{
					"username": "nefix",
					"password": "f0kt3Rf$",
				}
			},
			ExpectedRedirect: "",
			ExpectedErr:      fmt.Errorf("login: %w: local: user not found", provider.ErrInvalidCredentials).Error(),
		},
		"should return an error if the user and password don't match": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{
					map[string]interface{}{
						"id":                   "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":                  "nefix",
						"username":             "nefix",
						"password":             "holiii :D",
						"password_reset_token": "",
						"provider":             "local",
						"active":               true,
						"category":             "default",
						"role":                 "user",
						"group":                "default-default",
						"name":                 "Néfix Estrada",
						"email":                "nefix@example.org",
						"email_verified":       &now,
					},
				}, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() map[string]string {
				return map[string]string{
					"username": "nefix",
					"password": "f0kt3Rf$",
				}
			},
			ExpectedRedirect: "",
			ExpectedErr:      fmt.Errorf("login: %w: local: invalid password", provider.ErrInvalidCredentials).Error(),
		},
		"should return an error if the user is disabled": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{
					map[string]interface{}{
						"id":                   "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":                  "nefix",
						"username":             "nefix",
						"password":             "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm",
						"password_reset_token": "",
						"provider":             "local",
						"active":               false,
						"category":             "default",
						"role":                 "user",
						"group":                "default-default",
						"name":                 "Néfix Estrada",
						"email":                "nefix@example.org",
						"email_verified":       &now,
					},
				}, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() map[string]string {
				return map[string]string{
					"username": "nefix",
					"password": "f0kt3Rf$",
				}
			},
			ExpectedRedirect: "",
			ExpectedErr:      provider.ErrUserDisabled.Error(),
		},
		"should return a DisclaimerAcknowledgementRequired token if the disclaimer acknowledgement is required": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{
					map[string]interface{}{
						"id":                   "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":                  "nefix",
						"username":             "nefix",
						"password":             "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
						"password_reset_token": "",
						"provider":             "local",
						"active":               true,
						"category":             "default",
						"role":                 "user",
						"group":                "default-default",
						"name":                 "Néfix Estrada",
						"email":                "nefix@example.org",
						"email_verified":       nil,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiMock.Client) {
				c.On("AdminUserRequiredDisclaimerAcknowledgement", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(true, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() map[string]string {
				return map[string]string{
					"username": "nefix",
					"password": "f0kt3Rf$",
				}
			},
			CheckToken: func(ss string) {
				claims, err := token.ParseDisclaimerAcknowledgementRequiredToken("", ss)
				assert.NoError(err)

				// Ensure the expiration time is correct
				assert.True(claims.ExpiresAt.Time.Before(time.Now().Add(11 * time.Minute)))
				assert.True(claims.ExpiresAt.Time.After(time.Now().Add(9 * time.Minute)))

				claims.ExpiresAt = nil
				claims.IssuedAt = nil
				claims.NotBefore = nil

				assert.Equal(&token.DisclaimerAcknowledgementRequiredClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						Type:  token.TypeDisclaimerAcknowledgementRequired,
						KeyID: "isardvdi",
					},
					UserID: "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
				}, claims)
			},
			ExpectedRedirect: "",
		},
		"should return a EmailVerificationRequired token if the email verification is required": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{
					map[string]interface{}{
						"id":                   "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":                  "nefix",
						"username":             "nefix",
						"password":             "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
						"password_reset_token": "",
						"provider":             "local",
						"active":               true,
						"category":             "default",
						"role":                 "user",
						"group":                "default-default",
						"name":                 "Néfix Estrada",
						"email":                "nefix@example.org",
						"email_verified":       nil,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiMock.Client) {
				c.On("AdminUserRequiredDisclaimerAcknowledgement", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
				c.On("AdminUserRequiredEmailVerification", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(true, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() map[string]string {
				return map[string]string{
					"username": "nefix",
					"password": "f0kt3Rf$",
				}
			},
			CheckToken: func(ss string) {
				claims, err := token.ParseEmailVerificationRequiredToken("", ss)
				assert.NoError(err)

				// Ensure the expiration time is correct
				assert.True(claims.ExpiresAt.Time.Before(time.Now().Add(11 * time.Minute)))
				assert.True(claims.ExpiresAt.Time.After(time.Now().Add(9 * time.Minute)))

				claims.ExpiresAt = nil
				claims.IssuedAt = nil
				claims.NotBefore = nil

				assert.Equal(&token.EmailVerificationRequiredClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						Type:  token.TypeEmailVerificationRequired,
						KeyID: "isardvdi",
					},
					UserID:       "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					CategoryID:   "default",
					CurrentEmail: "nefix@example.org",
				}, claims)
			},
			ExpectedRedirect: "",
		},
		"should return a PasswordResetRequired token if the user needs to reset their password": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{
					map[string]interface{}{
						"id":                   "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":                  "nefix",
						"username":             "nefix",
						"password":             "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
						"password_reset_token": "",
						"provider":             "local",
						"active":               true,
						"category":             "default",
						"role":                 "user",
						"group":                "default-default",
						"name":                 "Néfix Estrada",
						"email":                "nefix@example.org",
						"email_verified":       nil,
					},
				}, nil)
			},
			PrepareAPI: func(c *apiMock.Client) {
				c.On("AdminUserRequiredDisclaimerAcknowledgement", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
				c.On("AdminUserRequiredEmailVerification", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(false, nil)
				c.On("AdminUserRequiredPasswordReset", mock.AnythingOfType("context.backgroundCtx"), "08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Return(true, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() map[string]string {
				return map[string]string{
					"username": "nefix",
					"password": "f0kt3Rf$",
				}
			},
			CheckToken: func(ss string) {
				claims, err := token.ParsePasswordResetRequiredToken("", ss)
				assert.NoError(err)

				// Ensure the expiration time is correct
				assert.True(claims.ExpiresAt.Time.Before(time.Now().Add(61 * time.Minute)))
				assert.True(claims.ExpiresAt.Time.After(time.Now().Add(59 * time.Minute)))

				claims.ExpiresAt = nil
				claims.IssuedAt = nil
				claims.NotBefore = nil

				assert.Equal(&token.PasswordResetRequiredClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						Type:  token.TypePasswordResetRequired,
						KeyID: "isardvdi",
					},
					UserID: "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
				}, claims)
			},
			ExpectedRedirect: "",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			cfg := cfg.New()
			log := log.New("authentication-test", "debug")
			dbMock := r.NewMock()
			apiMock := &apiMock.Client{}

			tc.PrepareDB(dbMock)

			if tc.PrepareAPI != nil {
				tc.PrepareAPI(apiMock)
			}

			a := authentication.Init(cfg, log, dbMock)
			a.Client = apiMock

			tkn, redirect, err := a.Login(context.Background(), tc.Provider, tc.CategoryID, tc.PrepareArgs())

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

func TestCheck(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)
	now := float64(time.Now().Unix())

	cases := map[string]struct {
		PrepareToken func() string
		ExpectedErr  string
	}{
		"should work if the token is a valid login token": {
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
					EmailVerified:          &now,
					DisclaimerAcknowledged: true,
				})
				require.NoError(err)

				return ss
			},
		},
		"should return an error if the token is invalid": {
			PrepareToken: func() string {
				ss, err := token.SignLoginToken("", -time.Hour, &model.User{
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
			ExpectedErr: "error parsing the JWT token: token has invalid claims: token is expired",
		},
		"should return an error if the token is not of type login": {
			PrepareToken: func() string {
				ss, err := token.SignDisclaimerAcknowledgementRequiredToken("", "néfix :D")
				require.NoError(err)

				return ss
			},
			ExpectedErr: "error parsing the JWT token: token has invalid claims: invalid token type",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			cfg := cfg.New()
			log := log.New("authentication-test", "debug")

			a := authentication.Init(cfg, log, nil)

			err := a.Check(context.Background(), tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}
		})
	}
}
