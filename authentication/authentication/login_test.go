package authentication_test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/token"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	apiMock "gitlab.com/isard/isardvdi-sdk-go/mock"
	"go.nhat.io/grpcmock"
	"google.golang.org/protobuf/types/known/timestamppb"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestLogin(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)
	now := float64(time.Now().Unix())

	cases := map[string]struct {
		PrepareDB       func(*r.Mock)
		PrepareAPI      func(*apiMock.Client)
		PrepareSessions func(*grpcmock.Server)

		RemoteAddr  string
		Provider    string
		CategoryID  string
		PrepareArgs func() provider.LoginArgs

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
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/New").WithPayload(&sessionsv1.NewRequest{
					UserId:     "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
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
			RemoteAddr: "127.0.0.1",
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				username := "nefix"
				password := "f0kt3Rf$"

				return provider.LoginArgs{
					FormUsername: &username,
					FormPassword: &password,
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
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/New").WithPayload(&sessionsv1.NewRequest{
					UserId:     "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
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
			RemoteAddr: "127.0.0.1",
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				ss, err := token.SignDisclaimerAcknowledgementRequiredToken("", "08fff46e-cbd3-40d2-9d8e-e2de7a8da654")
				require.NoError(err)

				return provider.LoginArgs{
					Token: &ss,
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
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/New").WithPayload(&sessionsv1.NewRequest{
					UserId:     "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
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
			RemoteAddr: "127.0.0.1",
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				ss, err := token.SignPasswordResetRequiredToken("", "08fff46e-cbd3-40d2-9d8e-e2de7a8da654")
				require.NoError(err)

				return provider.LoginArgs{
					Token: &ss,
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
			RemoteAddr: "127.0.0.1",
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				username := "nefix"
				password := "f0kt3Rf$"

				return provider.LoginArgs{
					FormUsername: &username,
					FormPassword: &password,
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
			RemoteAddr: "127.0.0.1",
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				username := "nefix"
				password := "f0kt3Rf$"

				return provider.LoginArgs{
					FormUsername: &username,
					FormPassword: &password,
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
			RemoteAddr: "127.0.0.1",
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				username := "nefix"
				password := "f0kt3Rf$"

				return provider.LoginArgs{
					FormUsername: &username,
					FormPassword: &password,
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
			PrepareArgs: func() provider.LoginArgs {
				username := "nefix"
				password := "f0kt3Rf$"

				return provider.LoginArgs{
					FormUsername: &username,
					FormPassword: &password,
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
			RemoteAddr: "127.0.0.1",
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				username := "nefix"
				password := "f0kt3Rf$"

				return provider.LoginArgs{
					FormUsername: &username,
					FormPassword: &password,
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
			RemoteAddr: "127.0.0.1",
			Provider:   "form",
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				username := "nefix"
				password := "f0kt3Rf$"

				return provider.LoginArgs{
					FormUsername: &username,
					FormPassword: &password,
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
			ctx := context.Background()

			cfg := cfg.New()
			log := log.New("authentication-test", "debug")

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			apiMock := &apiMock.Client{}
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

			a := authentication.Init(cfg, log, dbMock, nil, nil, sessionsCli)
			a.API = apiMock

			tkn, redirect, err := a.Login(ctx, tc.Provider, tc.CategoryID, tc.PrepareArgs(), tc.RemoteAddr)

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
