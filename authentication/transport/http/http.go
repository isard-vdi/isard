package http

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net/http"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/db"
	oasAuthentication "gitlab.com/isard/isardvdi/pkg/gen/oas/authentication"

	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-sdk-go"
)

var _ oasAuthentication.Handler = &AuthenticationServer{}

type AuthenticationServer struct {
	Addr           string
	Authentication authentication.Interface

	Log *zerolog.Logger
	WG  *sync.WaitGroup
}

func Serve(ctx context.Context, wg *sync.WaitGroup, log *zerolog.Logger, addr string, auth authentication.Interface) {
	a := &AuthenticationServer{
		Addr:           addr,
		Authentication: auth,
		Log:            log,
		WG:             wg,
	}

	sec := &SecurityHandler{}

	// TODO: Security handler
	oas, err := oasAuthentication.NewServer(a, sec)
	if err != nil {
		log.Fatal().Err(err).Msg("create the OpenAPI authentication server")
	}

	m := http.NewServeMux()

	// SAML authentication
	m.HandleFunc("/saml/login", a.loginSAML)
	m.HandleFunc("/saml/metadata", a.Authentication.SAML().ServeMetadata)
	m.HandleFunc("/saml/acs", a.Authentication.SAML().ServeACS)

	m.Handle("/", oas)

	s := http.Server{
		Addr:    a.Addr,
		Handler: m,
	}

	go func() {
		if err := s.ListenAndServe(); err != nil {
			log.Fatal().Err(err).Str("addr", addr).Msg("serve http")
		}
	}()

	<-ctx.Done()

	timeout, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	s.Shutdown(timeout)
	a.WG.Done()
}

func (a *AuthenticationServer) loginSAML(w http.ResponseWriter, r *http.Request) {
	// Hijack the URL to ensure the redirect has the correct path
	r.URL.Path = "/authentication/login"
	a.Authentication.SAML().HandleStartAuthFlow(w, r)
}

func (a *AuthenticationServer) Login(ctx context.Context, req oasAuthentication.OptLoginRequestMultipart, params oasAuthentication.LoginParams) (oasAuthentication.LoginRes, error) {
	args := map[string]string{}

	// Token provided in the Authorization header
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if ok {
		args[provider.TokenArgsKey] = tkn
	}

	// Redirect the user after login
	if params.Redirect.Set {
		args[provider.RedirectArgsKey] = params.Redirect.Value
	}

	// Form parameters (username + password)
	if req.Set && req.Value.Username.Set {
		args["username"] = req.Value.Username.Value
	}

	if req.Set && req.Value.Password.Set {
		args["password"] = req.Value.Password.Value
	}

	p := a.Authentication.Provider(string(params.Provider))
	if p.String() == provider.SAMLString {
		c := &http.Cookie{
			Name:  "token",
			Value: params.Token.Value,
		}
		r := &http.Request{
			Header: http.Header{
				"Cookie": []string{c.String()},
			},
		}

		if _, err := a.Authentication.SAML().Session.GetSession(r); err != nil {
			// Redirect to the correct SAML endpoint
			return &oasAuthentication.LoginFound{
				Location: "/authentication/saml/login",
			}, nil
		}
	}

	tkn, redirect, err := a.Authentication.Login(ctx, p.String(), params.CategoryID, args)
	if err != nil {
		if errors.Is(err, provider.ErrInvalidCredentials) {
			return &oasAuthentication.LoginUnauthorized{
				Data: bytes.NewReader([]byte(err.Error())),
			}, nil
		}

		if errors.Is(err, provider.ErrUserDisabled) {
			return &oasAuthentication.LoginForbidden{
				Data: bytes.NewReader([]byte(err.Error())),
			}, nil
		}

		return nil, err
	}

	c := &http.Cookie{
		Name:    "authorization",
		Path:    "/",
		Value:   tkn,
		Expires: time.Now().Add(5 * time.Minute),
	}
	cookie := c.String()

	if redirect != "" {
		return &oasAuthentication.LoginFound{
			Location:      redirect,
			Authorization: fmt.Sprintf("Bearer %s", tkn),
			SetCookie:     oasAuthentication.NewOptString(cookie),
		}, nil
	}

	return &oasAuthentication.LoginOKHeaders{
		Authorization: fmt.Sprintf("Bearer %s", tkn),
		SetCookie:     cookie,
		Response: oasAuthentication.LoginOK{
			Data: bytes.NewReader([]byte(tkn)),
		},
	}, nil
}

func (a *AuthenticationServer) Callback(ctx context.Context, params oasAuthentication.CallbackParams) (oasAuthentication.CallbackRes, error) {
	args := map[string]string{}

	// OAuth2
	if params.Code.Set {
		args["code"] = params.Code.Value
	}

	// SAML
	if params.Token.Set {
		c := &http.Cookie{
			Name:  "token",
			Value: params.Token.Value,
		}

		ctx = context.WithValue(ctx, provider.HTTPRequest, &http.Request{
			Header: http.Header{
				"Cookie": []string{c.String()},
			},
		})
	}

	tkn, redirect, err := a.Authentication.Callback(ctx, params.State, args)
	if err != nil {
		if errors.Is(err, provider.ErrUserDisabled) {
			return &oasAuthentication.CallbackFound{
				Location: "/login?error=user_disabled",
			}, nil
		}

		return nil, err
	}

	c := &http.Cookie{
		Name:    "authorization",
		Path:    "/",
		Value:   tkn,
		Expires: time.Now().Add(5 * time.Minute),
	}
	cookie := c.String()

	if redirect != "" {
		return &oasAuthentication.CallbackFound{
			Location:      redirect,
			Authorization: fmt.Sprintf("Bearer %s", tkn),
			SetCookie:     oasAuthentication.NewOptString(cookie),
		}, nil
	}

	return &oasAuthentication.CallbackOKHeaders{
		Authorization: fmt.Sprintf("Bearer %s", tkn),
		SetCookie:     cookie,
		Response: oasAuthentication.CallbackOK{
			Data: bytes.NewReader([]byte(tkn)),
		},
	}, nil
}

func (a *AuthenticationServer) Providers(ctx context.Context) (*oasAuthentication.ProvidersResponse, error) {
	providers := []oasAuthentication.Providers{}
	for _, p := range a.Authentication.Providers() {
		if p == provider.LocalString || p == provider.LDAPString {
			continue
		}

		var i oasAuthentication.Providers
		if err := i.UnmarshalText([]byte(p)); err != nil {
			a.Log.Error().Err(err).Msg("list providers")
			continue
		}

		providers = append(providers, i)
	}

	return &oasAuthentication.ProvidersResponse{
		Providers: providers,
	}, nil
}

func (a *AuthenticationServer) Check(ctx context.Context) (oasAuthentication.CheckRes, error) {
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.CheckUnauthorized{
			Type: oasAuthentication.CheckErrorTypeMissingToken,
			Msg:  "missing JWT token",
		}, nil
	}

	if err := a.Authentication.Check(ctx, tkn); err != nil {
		if !errors.Is(err, token.ErrInvalidToken) || !errors.Is(err, token.ErrInvalidTokenType) {
			return nil, fmt.Errorf("check JWT: %w", err)
		}

		return &oasAuthentication.CheckForbidden{
			Type: oasAuthentication.CheckErrorTypeInvalidToken,
			Msg:  err.Error(),
		}, nil
	}

	return &oasAuthentication.CheckResponse{}, nil
}

func (a *AuthenticationServer) AcknowledgeDisclaimer(ctx context.Context, req *oasAuthentication.AcknowledgeDisclaimerRequest) (oasAuthentication.AcknowledgeDisclaimerRes, error) {
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.AcknowledgeDisclaimerUnauthorized{
			Type: oasAuthentication.AcknowledgeDisclaimerErrorTypeMissingToken,
			Msg:  "missing JWT token",
		}, nil
	}

	if err := a.Authentication.AcknowledgeDisclaimer(ctx, tkn); err != nil {
		if errors.Is(err, token.ErrInvalidToken) || errors.Is(err, token.ErrInvalidTokenType) {
			return &oasAuthentication.AcknowledgeDisclaimerForbidden{
				Type: oasAuthentication.AcknowledgeDisclaimerErrorTypeInvalidToken,
				Msg:  err.Error(),
			}, nil
		}

		var dbErr *db.Err
		if !errors.As(err, &dbErr) {
			return &oasAuthentication.AcknowledgeDisclaimerInternalServerError{
				Type: oasAuthentication.AcknowledgeDisclaimerErrorTypeInternalServer,
				Msg:  "database error",
			}, nil
		}

		return &oasAuthentication.AcknowledgeDisclaimerInternalServerError{
			Type: oasAuthentication.AcknowledgeDisclaimerErrorTypeInternalServer,
			Msg:  "unknown error",
		}, nil
	}

	return &oasAuthentication.AcknowledgeDisclaimerResponse{}, nil
}

func (a *AuthenticationServer) RequestEmailVerification(ctx context.Context, req *oasAuthentication.RequestEmailVerificationRequest) (oasAuthentication.RequestEmailVerificationRes, error) {
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.RequestEmailVerificationUnauthorized{
			Type: oasAuthentication.RequestEmailVerificationErrorTypeMissingToken,
			Msg:  "missing JWT token",
		}, nil
	}

	if err := a.Authentication.RequestEmailVerification(ctx, tkn, req.Email); err != nil {
		if errors.Is(err, token.ErrInvalidToken) || errors.Is(err, token.ErrInvalidTokenType) {
			return &oasAuthentication.RequestEmailVerificationForbidden{
				Type: oasAuthentication.RequestEmailVerificationErrorTypeInvalidToken,
				Msg:  err.Error(),
			}, nil
		}

		if errors.Is(err, authentication.ErrInvalidEmail) {
			return &oasAuthentication.RequestEmailVerificationBadRequest{
				Type: oasAuthentication.RequestEmailVerificationErrorTypeInvalidEmail,
				Msg:  "invalid email",
			}, nil
		}

		if errors.Is(err, authentication.ErrEmailAlreadyInUse) {
			return &oasAuthentication.RequestEmailVerificationConflict{
				Type: oasAuthentication.RequestEmailVerificationErrorTypeEmailAlreadyInUse,
				Msg:  err.Error(),
			}, nil
		}

		var dbErr *db.Err
		if errors.As(err, &dbErr) {
			return &oasAuthentication.RequestEmailVerificationInternalServerError{
				Type: oasAuthentication.RequestEmailVerificationErrorTypeInternalServer,
				Msg:  "database error",
			}, nil
		}

		return &oasAuthentication.RequestEmailVerificationInternalServerError{
			Type: oasAuthentication.RequestEmailVerificationErrorTypeInternalServer,
			Msg:  "unknown error",
		}, nil
	}

	return &oasAuthentication.RequestEmailVerificationResponse{}, nil
}

func (a *AuthenticationServer) VerifyEmail(ctx context.Context, req *oasAuthentication.VerifyEmailRequest) (oasAuthentication.VerifyEmailRes, error) {
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.VerifyEmailUnauthorized{
			Type: oasAuthentication.VerifyEmailErrorTypeMissingToken,
			Msg:  "missing JWT token",
		}, nil
	}

	if err := a.Authentication.VerifyEmail(ctx, tkn); err != nil {
		if errors.Is(err, token.ErrInvalidToken) || errors.Is(err, token.ErrInvalidTokenType) {
			return &oasAuthentication.VerifyEmailForbidden{
				Type: oasAuthentication.VerifyEmailErrorTypeInvalidToken,
				Msg:  err.Error(),
			}, nil
		}

		var dbErr *db.Err
		if errors.As(err, &dbErr) {
			return &oasAuthentication.VerifyEmailInternalServerError{
				Type: oasAuthentication.VerifyEmailErrorTypeInternalServer,
				Msg:  "database error",
			}, nil
		}

		return &oasAuthentication.VerifyEmailInternalServerError{
			Type: oasAuthentication.VerifyEmailErrorTypeInternalServer,
			Msg:  "unknown error",
		}, nil
	}

	return &oasAuthentication.VerifyEmailResponse{}, nil
}

func (a *AuthenticationServer) ForgotPassword(ctx context.Context, req *oasAuthentication.ForgotPasswordRequest) (oasAuthentication.ForgotPasswordRes, error) {
	if err := a.Authentication.ForgotPassword(ctx, req.CategoryID, req.Email); err != nil {
		if errors.Is(err, token.ErrInvalidToken) || errors.Is(err, token.ErrInvalidTokenType) {
			return &oasAuthentication.ForgotPasswordForbidden{
				Type: oasAuthentication.ForgotPasswordErrorTypeInvalidToken,
				Msg:  err.Error(),
			}, nil
		}

		if errors.Is(err, authentication.ErrUserNotFound) {
			return &oasAuthentication.ForgotPasswordNotFound{
				Type: oasAuthentication.ForgotPasswordErrorTypeUserNotFound,
				Msg:  "user not found",
			}, nil
		}

		var dbErr *db.Err
		if errors.As(err, &dbErr) {
			return &oasAuthentication.ForgotPasswordInternalServerError{
				Type: oasAuthentication.ForgotPasswordErrorTypeInternalServer,
				Msg:  "database error",
			}, nil
		}

		return &oasAuthentication.ForgotPasswordInternalServerError{
			Type: oasAuthentication.ForgotPasswordErrorTypeInternalServer,
			Msg:  "unknown error",
		}, nil
	}

	return &oasAuthentication.ForgotPasswordResponse{}, nil
}

func (a *AuthenticationServer) ResetPassword(ctx context.Context, req *oasAuthentication.ResetPasswordRequest) (oasAuthentication.ResetPasswordRes, error) {
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.ResetPasswordUnauthorized{
			Type: oasAuthentication.ResetPasswordErrorTypeMissingToken,
			Msg:  "missing JWT token",
		}, nil
	}

	if err := a.Authentication.ResetPassword(ctx, tkn, req.Password); err != nil {
		if errors.Is(err, token.ErrInvalidToken) || errors.Is(err, token.ErrInvalidTokenType) {
			return &oasAuthentication.ResetPasswordForbidden{
				Type: oasAuthentication.ResetPasswordErrorTypeInvalidToken,
				Msg:  err.Error(),
			}, nil
		}

		var apiErr isardvdi.Err
		if errors.As(err, &apiErr) {
			if errors.Is(err, isardvdi.ErrBadRequest) {
				return &oasAuthentication.ResetPasswordBadRequest{
					Type: oasAuthentication.ResetPasswordErrorTypeBadRequest,
					Msg:  "bad request",
				}, nil
			}

			if errors.Is(err, isardvdi.ErrInternalServer) {
				return &oasAuthentication.ResetPasswordInternalServerError{
					Type: oasAuthentication.ResetPasswordErrorTypeInternalServer,
					Msg:  "api error",
				}, nil
			}

			return &oasAuthentication.ResetPasswordInternalServerError{
				Type: oasAuthentication.ResetPasswordErrorTypeInternalServer,
				Msg:  "unknown api error",
			}, nil
		}

		return &oasAuthentication.ResetPasswordInternalServerError{
			Type: oasAuthentication.ResetPasswordErrorTypeInternalServer,
			Msg:  "unknown error",
		}, nil
	}

	return &oasAuthentication.ResetPasswordResponse{}, nil
}
