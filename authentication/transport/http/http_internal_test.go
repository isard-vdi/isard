package http

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	nethttp "net/http"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/limits"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
	httpErr "gitlab.com/isard/isardvdi/authentication/transport/http/error"
	oasAuthentication "gitlab.com/isard/isardvdi/pkg/gen/oas/authentication"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/crewjam/saml"
	"github.com/crewjam/saml/samlsp"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestLogin(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		Provider              oasAuthentication.Providers
		PrepareToken          func() string
		PrepareAuthentication func(context.Context, *authentication.MockAuthentication, string)
		CheckResponse         func(string, oasAuthentication.LoginRes)
		Expected              oasAuthentication.LoginRes
		ExpectedErr           string
	}{
		"should work as expected": {
			PrepareToken: func() string {
				expiration := time.Date(2026, 8, 13, 12, 0, 0, 0, time.UTC)

				ss, err := token.SignLoginToken("", expiration, "ThoJuroQueEsUnID", &model.User{
					ID: "local-default-admin-admin",
				})
				require.NoError(err)

				return ss
			},
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, tkn string) {
				m.On("Login", ctx, types.ProviderForm, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return(tkn, "", nil)
			},
			CheckResponse: func(tkn string, res oasAuthentication.LoginRes) {
				assert.Equal(&oasAuthentication.LoginOKHeaders{
					Authorization: "Bearer " + tkn,
					SetCookie:     "authorization=" + tkn + "; Path=/; Expires=Thu, 13 Aug 2026 12:00:00 GMT; Secure; SameSite=Strict",
					Response: oasAuthentication.LoginOK{
						Data: bytes.NewReader([]byte(tkn)),
					},
				}, res)
			},
		},
		"should work as expected if the login returns a redirect": {
			PrepareToken: func() string {
				expiration := time.Date(2026, 8, 13, 12, 0, 0, 0, time.UTC)

				ss, err := token.SignLoginToken("", expiration, "ThoJuroQueEsUnID", &model.User{
					ID: "local-default-admin-admin",
				})
				require.NoError(err)

				return ss
			},
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, tkn string) {
				m.On("Login", ctx, types.ProviderForm, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return(tkn, "/", nil)
			},
			CheckResponse: func(tkn string, res oasAuthentication.LoginRes) {
				assert.Equal(&oasAuthentication.LoginFound{
					Location:  "/",
					SetCookie: oasAuthentication.NewOptString("authorization=" + tkn + "; Path=/; Expires=Thu, 13 Aug 2026 12:00:00 GMT; Secure; SameSite=Strict"),
				}, res)
			},
		},
		"should work as expected if the user has login notifications": {
			PrepareToken: func() string {
				expiration := time.Date(2026, 8, 13, 12, 0, 0, 0, time.UTC)

				ss, err := token.SignLoginToken("", expiration, "ThoJuroQueEsUnID", &model.User{
					ID: "local-default-admin-admin",
				})
				require.NoError(err)

				return ss
			},
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, tkn string) {
				m.On("Login", ctx, types.ProviderForm, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return(tkn, "/notifications/login", nil)
			},
			CheckResponse: func(tkn string, res oasAuthentication.LoginRes) {
				assert.Equal(&oasAuthentication.LoginOKHeaders{
					Location:      oasAuthentication.NewOptString("/notifications/login"),
					Authorization: "Bearer " + tkn,
					SetCookie:     "authorization=" + tkn + "; Path=/; Expires=Thu, 13 Aug 2026 12:00:00 GMT; Secure; SameSite=Strict",
					Response: oasAuthentication.LoginOK{
						Data: bytes.NewReader([]byte(tkn)),
					},
				}, res)
			},
		},
		"should return an unauthorized error if the credentials are invalid": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Login", ctx, types.ProviderForm, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "", provider.ErrInvalidCredentials)
			},
			Expected: &oasAuthentication.LoginUnauthorized{
				Error: oasAuthentication.LoginErrorErrorInvalidCredentials,
				Msg:   "invalid credentials",
			},
		},
		"should return a forbidden error if the user is disabled": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Login", ctx, types.ProviderForm, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "", provider.ErrUserDisabled)
			},
			Expected: &oasAuthentication.LoginForbidden{
				Error: oasAuthentication.LoginErrorErrorUserDisabled,
				Msg:   provider.ErrUserDisabled.Error(),
			},
		},
		"should return a forbidden error if the user is disallowed": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Login", ctx, types.ProviderForm, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "", provider.ErrUserDisallowed)
			},
			Expected: &oasAuthentication.LoginForbidden{
				Error: oasAuthentication.LoginErrorErrorUserDisallowed,
				Msg:   provider.ErrUserDisallowed.Error(),
			},
		},
		"should return a too many requests error if the user is rate limited": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				retryAfter := time.Date(2026, 8, 13, 12, 5, 0, 0, time.UTC)

				m.On("Login", ctx, types.ProviderForm, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "", &limits.RateLimitError{
					RetryAfter: retryAfter,
				})
			},
			Expected: &oasAuthentication.LoginTooManyRequestsHeaders{
				RetryAfter: "Thu, 13 Aug 2026 12:05:00 GMT",
				Response: oasAuthentication.LoginTooManyRequests{
					Data: bytes.NewBufferString("Retry after: Thu, 13 Aug 2026 12:05:00 GMT"),
				},
			},
		},
		"should return the user error if the provider fails": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Login", ctx, types.ProviderForm, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "", &provider.ProviderError{
					User:   provider.ErrUnknownIDP,
					Detail: errors.New("oh no"),
				})
			},
			ExpectedErr: provider.ErrUnknownIDP.Error(),
		},
		"should return an internal server error if the login fails": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Login", ctx, types.ProviderForm, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "", errors.New("oh no"))
			},
			ExpectedErr: provider.ErrInternal.Error(),
		},
		"should return an internal server error if the token expiration can't be read": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Login", ctx, types.ProviderForm, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return("notatoken", "", nil)
			},
			ExpectedErr: provider.ErrInternal.Error(),
		},
		"should redirect without setting the authorization cookie if the provider forces a redirect without a token": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Login", ctx, types.ProviderForm, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "/authentication/callback?state=eyJhbGciOiJIUzI1NiJ9", nil)
			},
			Expected: &oasAuthentication.LoginFound{
				Location: "/authentication/callback?state=eyJhbGciOiJIUzI1NiJ9",
			},
		},
		"should redirect without setting the authorization cookie if google forces a redirect": {
			Provider: oasAuthentication.ProvidersGoogle,
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Login", ctx, types.ProviderGoogle, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "https://accounts.google.com/o/oauth2/auth?client_id=isard&state=abc", nil)
			},
			Expected: &oasAuthentication.LoginFound{
				Location: "https://accounts.google.com/o/oauth2/auth?client_id=isard&state=abc",
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var tkn string
			if tc.PrepareToken != nil {
				tkn = tc.PrepareToken()
			}

			prv := tc.Provider
			if prv == "" {
				prv = oasAuthentication.ProvidersForm
			}

			prvMock := provider.NewMockProvider(t)
			prvMock.On("String").Return(string(prv))

			authMock := authentication.NewMockAuthentication(t)
			authMock.On("Provider", string(prv), "default").Return(prvMock)

			a := &AuthenticationServer{
				Authentication: authMock,
				Log:            log.New("test", "debug"),
			}

			ctx := context.WithValue(t.Context(), requestMetadataRemoteAddrCtxKey, "127.0.0.1")
			ctx = context.WithValue(ctx, requestMetadataHostCtxKey, "isard.example.org")

			tc.PrepareAuthentication(ctx, authMock, tkn)

			res, err := a.Login(ctx, oasAuthentication.OptLoginRequestMultipart{}, oasAuthentication.LoginParams{
				Provider:   prv,
				CategoryID: "default",
			})

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckResponse != nil {
				tc.CheckResponse(tkn, res)
			} else {
				assert.Equal(tc.Expected, res)
			}

			authMock.AssertExpectations(t)
			prvMock.AssertExpectations(t)
		})
	}
}

type establishedSAMLSession struct{}

func (establishedSAMLSession) CreateSession(_ nethttp.ResponseWriter, _ *nethttp.Request, _ *saml.Assertion) error {
	return nil
}

func (establishedSAMLSession) DeleteSession(_ nethttp.ResponseWriter, _ *nethttp.Request) error {
	return nil
}

func (establishedSAMLSession) GetSession(_ *nethttp.Request) (samlsp.Session, error) {
	return samlsp.JWTSessionClaims{}, nil
}

func TestLoginSAML(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	redirect := "/authentication/callback?state=eyJhbGciOiJIUzI1NiJ9"

	prvMock := provider.NewMockProvider(t)
	prvMock.On("String").Return(types.ProviderSAML)

	authMock := authentication.NewMockAuthentication(t)
	authMock.On("Provider", types.ProviderSAML, "default").Return(prvMock)
	authMock.On("SAML", "default", "isard.example.org").Return(&samlsp.Middleware{
		Session: establishedSAMLSession{},
	})

	a := &AuthenticationServer{
		Authentication: authMock,
		Log:            log.New("test", "debug"),
	}

	ctx := context.WithValue(t.Context(), requestMetadataRemoteAddrCtxKey, "127.0.0.1")
	ctx = context.WithValue(ctx, requestMetadataHostCtxKey, "isard.example.org")

	authMock.On("Login", ctx, types.ProviderSAML, "default", provider.LoginArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", redirect, nil)

	res, err := a.Login(ctx, oasAuthentication.OptLoginRequestMultipart{}, oasAuthentication.LoginParams{
		Provider:   oasAuthentication.ProvidersSaml,
		CategoryID: "default",
		Token:      oasAuthentication.NewOptString("saml-session-cookie"),
	})

	assert.NoError(err)
	assert.Equal(&oasAuthentication.LoginFound{
		Location: redirect,
	}, res)

	authMock.AssertExpectations(t)
	prvMock.AssertExpectations(t)
}

func TestCallback(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken          func() string
		PrepareAuthentication func(context.Context, *authentication.MockAuthentication, string)
		Params                oasAuthentication.CallbackParams
		CheckResponse         func(string, oasAuthentication.CallbackRes)
		Expected              oasAuthentication.CallbackRes
		ExpectedErr           string
	}{
		"should work as expected": {
			PrepareToken: func() string {
				expiration := time.Date(2026, 8, 13, 12, 0, 0, 0, time.UTC)

				ss, err := token.SignLoginToken("", expiration, "ThoJuroQueEsUnID", &model.User{
					ID: "local-default-admin-admin",
				})
				require.NoError(err)

				return ss
			},
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, tkn string) {
				m.On("Callback", ctx, "the callback token", provider.CallbackArgs{Host: "isard.example.org"}, "127.0.0.1").Return(tkn, "", nil)
			},
			Params: oasAuthentication.CallbackParams{
				State: "the callback token",
			},
			CheckResponse: func(tkn string, res oasAuthentication.CallbackRes) {
				assert.Equal(&oasAuthentication.CallbackOKHeaders{
					Authorization: "Bearer " + tkn,
					SetCookie:     "authorization=" + tkn + "; Path=/; Expires=Thu, 13 Aug 2026 12:00:00 GMT; Secure; SameSite=Strict",
					Response: oasAuthentication.CallbackOK{
						Data: bytes.NewReader([]byte(tkn)),
					},
				}, res)
			},
		},
		"should work as expected with an OAuth2 code": {
			PrepareToken: func() string {
				expiration := time.Date(2026, 8, 13, 12, 0, 0, 0, time.UTC)

				ss, err := token.SignLoginToken("", expiration, "ThoJuroQueEsUnID", &model.User{
					ID: "local-default-admin-admin",
				})
				require.NoError(err)

				return ss
			},
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, tkn string) {
				code := "the OAuth2 code"

				m.On("Callback", ctx, "the callback token", provider.CallbackArgs{Host: "isard.example.org", Oauth2Code: &code}, "127.0.0.1").Return(tkn, "/", nil)
			},
			Params: oasAuthentication.CallbackParams{
				State: "the callback token",
				Code:  oasAuthentication.NewOptString("the OAuth2 code"),
			},
			CheckResponse: func(tkn string, res oasAuthentication.CallbackRes) {
				assert.Equal(&oasAuthentication.CallbackFound{
					Location:  "/",
					SetCookie: oasAuthentication.NewOptString("authorization=" + tkn + "; Path=/; Expires=Thu, 13 Aug 2026 12:00:00 GMT; Secure; SameSite=Strict"),
				}, res)
			},
		},
		"should redirect to the login page if the user is disabled": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Callback", ctx, "the callback token", provider.CallbackArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "", provider.ErrUserDisabled)
			},
			Params: oasAuthentication.CallbackParams{
				State: "the callback token",
			},
			Expected: &oasAuthentication.CallbackFound{
				Location: "/login?error=" + string(httpErr.LoginUserDisabled),
			},
		},
		"should redirect to the login page if the user is disallowed": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Callback", ctx, "the callback token", provider.CallbackArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "", provider.ErrUserDisallowed)
			},
			Params: oasAuthentication.CallbackParams{
				State: "the callback token",
			},
			Expected: &oasAuthentication.CallbackFound{
				Location: "/login?error=" + string(httpErr.LoginUserDisallowed),
			},
		},
		"should return the user error if the provider fails": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Callback", ctx, "the callback token", provider.CallbackArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "", &provider.ProviderError{
					User:   provider.ErrUnknownIDP,
					Detail: errors.New("oh no"),
				})
			},
			Params: oasAuthentication.CallbackParams{
				State: "the callback token",
			},
			ExpectedErr: provider.ErrUnknownIDP.Error(),
		},
		"should return an internal server error if the callback fails": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Callback", ctx, "the callback token", provider.CallbackArgs{Host: "isard.example.org"}, "127.0.0.1").Return("", "", errors.New("oh no"))
			},
			Params: oasAuthentication.CallbackParams{
				State: "the callback token",
			},
			ExpectedErr: provider.ErrInternal.Error(),
		},
		"should return an internal server error if the token expiration can't be read": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Callback", ctx, "the callback token", provider.CallbackArgs{Host: "isard.example.org"}, "127.0.0.1").Return("notatoken", "", nil)
			},
			Params: oasAuthentication.CallbackParams{
				State: "the callback token",
			},
			ExpectedErr: provider.ErrInternal.Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var tkn string
			if tc.PrepareToken != nil {
				tkn = tc.PrepareToken()
			}

			authMock := authentication.NewMockAuthentication(t)

			a := &AuthenticationServer{
				Authentication: authMock,
				Log:            log.New("test", "debug"),
			}

			ctx := context.WithValue(t.Context(), requestMetadataRemoteAddrCtxKey, "127.0.0.1")
			ctx = context.WithValue(ctx, requestMetadataHostCtxKey, "isard.example.org")

			tc.PrepareAuthentication(ctx, authMock, tkn)

			res, err := a.Callback(ctx, tc.Params)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckResponse != nil {
				tc.CheckResponse(tkn, res)
			} else {
				assert.Equal(tc.Expected, res)
			}

			authMock.AssertExpectations(t)
		})
	}
}

func TestRenew(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken          func() string
		PrepareAuthentication func(context.Context, *authentication.MockAuthentication, string)
		Token                 string
		CheckResponse         func(string, oasAuthentication.RenewRes)
		Expected              oasAuthentication.RenewRes
	}{
		"should work as expected": {
			PrepareToken: func() string {
				expiration := time.Date(2026, 8, 13, 12, 0, 0, 0, time.UTC)

				ss, err := token.SignLoginToken("", expiration, "ThoJuroQueEsUnID", &model.User{
					ID: "local-default-admin-admin",
				})
				require.NoError(err)

				return ss
			},
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, renewed string) {
				m.On("Renew", ctx, "login token", "127.0.0.1").Return(renewed, nil)
			},
			Token: "login token",
			CheckResponse: func(renewed string, res oasAuthentication.RenewRes) {
				cookie := "authorization=" + renewed + "; Path=/; Expires=Thu, 13 Aug 2026 12:00:00 GMT; Secure; SameSite=Strict"

				assert.Equal(&oasAuthentication.RenewResponseHeaders{
					SetCookie: cookie,
					Response: oasAuthentication.RenewResponse{
						Token: renewed,
					},
				}, res)
			},
		},
		"should return an unauthorized error if there's no token in the context": {
			Expected: &oasAuthentication.RenewUnauthorized{
				Error: oasAuthentication.RenewErrorErrorMissingToken,
				Msg:   "missing JWT token",
			},
		},
		"should return an unauthorized error if the token is not a login token": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Renew", ctx, "register token", "127.0.0.1").Return("", fmt.Errorf("%w: %w", token.ErrInvalidToken, token.ErrInvalidTokenType))
			},
			Token: "register token",
			Expected: &oasAuthentication.RenewUnauthorized{
				Error: oasAuthentication.RenewErrorErrorInvalidSession,
				Msg:   "invalid JWT token: invalid token type",
			},
		},
		"should return an unauthorized error if the token is malformed": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Renew", ctx, "melina's token", "127.0.0.1").Return("", fmt.Errorf("%w: %w", token.ErrInvalidToken, jwt.ErrTokenMalformed))
			},
			Token: "melina's token",
			Expected: &oasAuthentication.RenewUnauthorized{
				Error: oasAuthentication.RenewErrorErrorInvalidSession,
				Msg:   "invalid JWT token: token is malformed",
			},
		},
		"should return an unauthorized error if the session is not found": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Renew", ctx, "login token", "127.0.0.1").Return("", fmt.Errorf("renew token: %w", status.Error(codes.NotFound, "session not found")))
			},
			Token: "login token",
			Expected: &oasAuthentication.RenewUnauthorized{
				Error: oasAuthentication.RenewErrorErrorInvalidSession,
				Msg:   "session expired",
			},
		},
		"should return an internal server error if the sessions service fails": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Renew", ctx, "login token", "127.0.0.1").Return("", fmt.Errorf("renew token: %w", status.Error(codes.Internal, "oh no")))
			},
			Token: "login token",
			Expected: &oasAuthentication.RenewInternalServerError{
				Error: oasAuthentication.RenewErrorErrorInternalServer,
				Msg:   "unknown renew sessions error",
			},
		},
		"should return an internal server error if the renewal fails": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Renew", ctx, "login token", "127.0.0.1").Return("", errors.New("oh no"))
			},
			Token: "login token",
			Expected: &oasAuthentication.RenewInternalServerError{
				Error: oasAuthentication.RenewErrorErrorInternalServer,
				Msg:   "unknown error",
			},
		},
		"should return an internal server error if the token expiration can't be read": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication, _ string) {
				m.On("Renew", ctx, "login token", "127.0.0.1").Return("notatoken", nil)
			},
			Token: "login token",
			Expected: &oasAuthentication.RenewInternalServerError{
				Error: oasAuthentication.RenewErrorErrorInternalServer,
				Msg:   "unknown error",
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			authMock := authentication.NewMockAuthentication(t)

			a := &AuthenticationServer{
				Authentication: authMock,
				Log:            log.New("test", "debug"),
			}

			var tkn string
			if tc.PrepareToken != nil {
				tkn = tc.PrepareToken()
			}

			ctx := context.WithValue(t.Context(), requestMetadataRemoteAddrCtxKey, "127.0.0.1")
			if tc.Token != "" {
				ctx = context.WithValue(ctx, tokenCtxKey, tc.Token)
			}

			if tc.PrepareAuthentication != nil {
				tc.PrepareAuthentication(ctx, authMock, tkn)
			}

			res, err := a.Renew(ctx, &oasAuthentication.RenewRequest{})

			assert.NoError(err)

			if tc.CheckResponse != nil {
				tc.CheckResponse(tkn, res)
			} else {
				assert.Equal(tc.Expected, res)
			}

			authMock.AssertExpectations(t)
		})
	}
}

func TestLogout(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareAuthentication func(context.Context, *authentication.MockAuthentication)
		Token                 string
		Expected              oasAuthentication.LogoutRes
	}{
		"should work as expected": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Logout", ctx, "login token").Return("", nil)
			},
			Token:    "login token",
			Expected: &oasAuthentication.LogoutResponse{},
		},
		"should work as expected if the provider returns a redirect": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Logout", ctx, "login token").Return("/authentication/saml/slo", nil)
			},
			Token: "login token",
			Expected: &oasAuthentication.LogoutResponse{
				Redirect: oasAuthentication.NewOptString("/authentication/saml/slo"),
			},
		},
		"should return an unauthorized error if there's no token in the context": {
			Expected: &oasAuthentication.LogoutUnauthorized{
				Error: oasAuthentication.LogoutErrorErrorMissingToken,
				Msg:   "missing JWT token",
			},
		},
		"should return an unauthorized error if the token is expired": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Logout", ctx, "login token").Return("", fmt.Errorf("%w: %w", token.ErrInvalidToken, jwt.ErrTokenExpired))
			},
			Token: "login token",
			Expected: &oasAuthentication.LogoutUnauthorized{
				Error: oasAuthentication.LogoutErrorErrorInvalidSession,
				Msg:   "session has expired",
			},
		},
		"should return an unauthorized error if the token is not a login token": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Logout", ctx, "register token").Return("", fmt.Errorf("%w: %w", token.ErrInvalidToken, token.ErrInvalidTokenType))
			},
			Token: "register token",
			Expected: &oasAuthentication.LogoutUnauthorized{
				Error: oasAuthentication.LogoutErrorErrorInvalidSession,
				Msg:   "invalid JWT token: invalid token type",
			},
		},
		"should return an internal server error if the sessions service fails": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Logout", ctx, "login token").Return("", fmt.Errorf("revoke session: %w", status.Error(codes.Internal, "oh no")))
			},
			Token: "login token",
			Expected: &oasAuthentication.LogoutInternalServerError{
				Error: oasAuthentication.LogoutErrorErrorInternalServer,
				Msg:   "unknown logout sessions error",
			},
		},
		"should return an internal server error if the logout fails": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Logout", ctx, "login token").Return("", errors.New("oh no"))
			},
			Token: "login token",
			Expected: &oasAuthentication.LogoutInternalServerError{
				Error: oasAuthentication.LogoutErrorErrorInternalServer,
				Msg:   "unknown error",
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			authMock := authentication.NewMockAuthentication(t)

			a := &AuthenticationServer{
				Authentication: authMock,
				Log:            log.New("test", "debug"),
			}

			ctx := context.WithValue(t.Context(), requestMetadataRemoteAddrCtxKey, "127.0.0.1")
			if tc.Token != "" {
				ctx = context.WithValue(ctx, tokenCtxKey, tc.Token)
			}

			if tc.PrepareAuthentication != nil {
				tc.PrepareAuthentication(ctx, authMock)
			}

			res, err := a.Logout(ctx, &oasAuthentication.LogoutRequest{})

			assert.NoError(err)
			assert.Equal(tc.Expected, res)

			authMock.AssertExpectations(t)
		})
	}
}

func TestCheck(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareAuthentication func(context.Context, *authentication.MockAuthentication)
		Token                 string
		Expected              oasAuthentication.CheckRes
		ExpectedErr           string
	}{
		"should work as expected": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Check", ctx, "login token", "127.0.0.1").Return(nil)
			},
			Token:    "login token",
			Expected: &oasAuthentication.CheckResponse{},
		},
		"should return an unauthorized error if there's no token in the context": {
			Expected: &oasAuthentication.CheckUnauthorized{
				Error: oasAuthentication.CheckErrorErrorMissingToken,
				Msg:   "missing JWT token",
			},
		},
		"should return a forbidden error if the token is not a login token": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Check", ctx, "register token", "127.0.0.1").Return(fmt.Errorf("%w: %w", token.ErrInvalidToken, token.ErrInvalidTokenType))
			},
			Token: "register token",
			Expected: &oasAuthentication.CheckForbidden{
				Error: oasAuthentication.CheckErrorErrorInvalidToken,
				Msg:   "invalid JWT token: invalid token type",
			},
		},
		"should return a forbidden error if the token is malformed": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Check", ctx, "melina's token", "127.0.0.1").Return(fmt.Errorf("%w: %w", token.ErrInvalidToken, jwt.ErrTokenMalformed))
			},
			Token: "melina's token",
			Expected: &oasAuthentication.CheckForbidden{
				Error: oasAuthentication.CheckErrorErrorInvalidToken,
				Msg:   "invalid JWT token: token is malformed",
			},
		},
		"should return a forbidden error if the session is not found": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Check", ctx, "login token", "127.0.0.1").Return(fmt.Errorf("get the session: %w", status.Error(codes.NotFound, "session not found")))
			},
			Token: "login token",
			Expected: &oasAuthentication.CheckForbidden{
				Error: oasAuthentication.CheckErrorErrorInvalidToken,
				Msg:   "session expired",
			},
		},
		"should return an internal server error if the sessions service fails": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Check", ctx, "login token", "127.0.0.1").Return(fmt.Errorf("get the session: %w", status.Error(codes.Internal, "oh no")))
			},
			Token: "login token",
			Expected: &oasAuthentication.CheckInternalServerError{
				Error: oasAuthentication.CheckErrorErrorInternalServer,
				Msg:   "unknown check sessions error",
			},
		},
		"should return an error if the check fails": {
			PrepareAuthentication: func(ctx context.Context, m *authentication.MockAuthentication) {
				m.On("Check", ctx, "login token", "127.0.0.1").Return(errors.New("oh no"))
			},
			Token:       "login token",
			ExpectedErr: "check JWT: oh no",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			authMock := authentication.NewMockAuthentication(t)

			a := &AuthenticationServer{
				Authentication: authMock,
				Log:            log.New("test", "debug"),
			}

			ctx := context.WithValue(t.Context(), requestMetadataRemoteAddrCtxKey, "127.0.0.1")
			if tc.Token != "" {
				ctx = context.WithValue(ctx, tokenCtxKey, tc.Token)
			}

			if tc.PrepareAuthentication != nil {
				tc.PrepareAuthentication(ctx, authMock)
			}

			res, err := a.Check(ctx)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.Expected, res)

			authMock.AssertExpectations(t)
		})
	}
}
