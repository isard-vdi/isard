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
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/golang-jwt/jwt"
	"github.com/stretchr/testify/assert"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestLogin(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB func(*r.Mock)

		Provider   string
		CategoryID string
		Args       map[string]string

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
						"id":             "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":            "nefix",
						"username":       "nefix",
						"password":       "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
						"provider":       "local",
						"active":         true,
						"category":       "default",
						"role":           "user",
						"group":          "default-default",
						"name":           "Néfix Estrada",
						"email":          "nefix@example.org",
						"email_verified": true,
					},
				}, nil)
				m.On(r.Table("users").Get("08fff46e-cbd3-40d2-9d8e-e2de7a8da654")).Return([]interface{}{
					map[string]interface{}{
						"id":             "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":            "nefix",
						"username":       "nefix",
						"password":       "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
						"provider":       "local",
						"active":         true,
						"category":       "default",
						"role":           "user",
						"group":          "default-default",
						"name":           "Néfix Estrada",
						"email":          "nefix@example.org",
						"email_verified": true,
					},
				}, nil)
				m.On(r.Table("users").Get("08fff46e-cbd3-40d2-9d8e-e2de7a8da654").Update(map[string]interface{}{
					"id":                       "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					"uid":                      "nefix",
					"username":                 "nefix",
					"password":                 "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
					"provider":                 "local",
					"active":                   true,
					"category":                 "default",
					"role":                     "user",
					"group":                    "default-default",
					"name":                     "Néfix Estrada",
					"email":                    "nefix@example.org",
					"email_verified":           true,
					"email_verification_token": "",
					"photo":                    "",
					"accessed":                 r.MockAnything(),
				})).Return(r.WriteResponse{
					Updated: 1,
				}, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			Args: map[string]string{
				"username": "nefix",
				"password": "f0kt3Rf$",
			},
			CheckToken: func(ss string) {
				tkn, typ, err := token.VerifyToken(nil, "", ss)

				assert.NoError(err)
				assert.Equal(token.TypeLogin, typ)

				claims := tkn.Claims.(*token.LoginClaims)

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
			Args: map[string]string{
				"username": "nefix",
				"password": "f0kt3Rf$",
			},
			ExpectedRedirect: "",
			ExpectedErr:      fmt.Errorf("login: %w", provider.ErrInvalidCredentials).Error(),
		},
		"should return an error if the user and password don't match": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{
					map[string]interface{}{
						"id":             "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":            "nefix",
						"username":       "nefix",
						"password":       "holiii :D",
						"provider":       "local",
						"active":         true,
						"category":       "default",
						"role":           "user",
						"group":          "default-default",
						"name":           "Néfix Estrada",
						"email":          "nefix@example.org",
						"email_verified": true,
					},
				}, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			Args: map[string]string{
				"username": "nefix",
				"password": "f0kt3Rf$",
			},
			ExpectedRedirect: "",
			ExpectedErr:      fmt.Errorf("login: %w", provider.ErrInvalidCredentials).Error(),
		},
		"should return an error if the user is disabled": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{
					map[string]interface{}{
						"id":             "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":            "nefix",
						"username":       "nefix",
						"password":       "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm",
						"provider":       "local",
						"active":         false,
						"category":       "default",
						"role":           "user",
						"group":          "default-default",
						"name":           "Néfix Estrada",
						"email":          "nefix@example.org",
						"email_verified": true,
					},
				}, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			Args: map[string]string{
				"username": "nefix",
				"password": "f0kt3Rf$",
			},
			ExpectedRedirect: "",
			ExpectedErr:      provider.ErrUserDisabled.Error(),
		},
		"should return a EmailValidationRequired token if the email validation is required and the email is not validated": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "nefix"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{
					map[string]interface{}{
						"id":             "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"uid":            "nefix",
						"username":       "nefix",
						"password":       "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
						"provider":       "local",
						"active":         true,
						"category":       "default",
						"role":           "user",
						"group":          "default-default",
						"name":           "Néfix Estrada",
						"email":          "nefix@example.org",
						"email_verified": false,
					},
				}, nil)
			},
			Provider:   "form",
			CategoryID: "default",
			Args: map[string]string{
				"username": "nefix",
				"password": "f0kt3Rf$",
			},
			CheckToken: func(ss string) {
				tkn, typ, err := token.VerifyToken(nil, "", ss)

				assert.NoError(err)
				assert.Equal(token.TypeEmailValidationRequired, typ)

				claims := tkn.Claims.(*token.EmailValidationRequiredClaims)

				expires := time.Unix(claims.StandardClaims.ExpiresAt, 0)

				// Ensure the expiration time is correct
				assert.True(expires.Before(time.Now().Add(61 * time.Minute)))
				assert.True(expires.After(time.Now().Add(59 * time.Minute)))

				claims.ExpiresAt = 0
				assert.Equal(&token.EmailValidationRequiredClaims{
					TypeClaims: token.TypeClaims{
						StandardClaims: &jwt.StandardClaims{
							Issuer: "isard-authentication",
						},
						Type:  token.TypeEmailValidationRequired,
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
			mock := r.NewMock()

			tc.PrepareDB(mock)

			a := authentication.Init(cfg, log, mock)
			tkn, redirect, err := a.Login(context.Background(), tc.Provider, tc.CategoryID, tc.Args)

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

			mock.AssertExpectations(t)
		})
	}
}
