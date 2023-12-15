package http

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	oasAuthentication "gitlab.com/isard/isardvdi/pkg/gen/oas/authentication"

	"github.com/crewjam/saml/samlsp"
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-sdk-go"
)

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

	// Non OAS endpoints
	m.HandleFunc("/login", a.login)
	m.HandleFunc("/callback", a.callback)

	// SAML authentication
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

func (a *AuthenticationServer) login(w http.ResponseWriter, r *http.Request) {
	args, err := parseArgs(r)
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte(err.Error()))
		return
	}

	if args[provider.TokenArgsKey] == "" {
		if err := requiredArgs([]string{provider.ProviderArgsKey, provider.CategoryIDArgsKey}, args); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte(err.Error()))
			time.Sleep(2 * time.Second)
			return
		}
	}

	prv := args[provider.ProviderArgsKey]
	cID := args[provider.CategoryIDArgsKey]

	// Handle SAML authentication
	p := a.Authentication.Provider(prv)
	if p.String() == provider.SAMLString {
		_, err := a.Authentication.SAML().Session.GetSession(r)
		if err != nil {
			if err == samlsp.ErrNoSession {
				// Hijack the URL to ensure the redirect has the correct path
				r.URL.Path = "/authentication/login"

				a.Authentication.SAML().HandleStartAuthFlow(w, r)
				time.Sleep(2 * time.Second)
				return
			}

			a.Authentication.SAML().OnError(w, r, err)
			time.Sleep(2 * time.Second)
			return
		}
	}

	tkn, redirect, err := a.Authentication.Login(r.Context(), prv, cID, args)
	if err != nil {
		if errors.Is(err, provider.ErrInvalidCredentials) {
			w.WriteHeader(http.StatusUnauthorized)
			w.Write([]byte(err.Error()))
			time.Sleep(2 * time.Second)
			return
		}

		if errors.Is(err, provider.ErrUserDisabled) {
			w.WriteHeader(http.StatusForbidden)
			w.Write([]byte(err.Error()))
			time.Sleep(2 * time.Second)
			return
		}

		// TODO: Better error handling!
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(err.Error()))
		time.Sleep(2 * time.Second)
		return
	}

	w.Header().Set("Authorization", "Bearer "+tkn)
	c := &http.Cookie{
		Name:    "authorization",
		Path:    "/",
		Value:   tkn,
		Expires: time.Now().Add(5 * time.Minute),
	}
	http.SetCookie(w, c)

	if redirect != "" {
		http.Redirect(w, r, redirect, http.StatusFound)
		return
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte(tkn))
}

func (a *AuthenticationServer) callback(w http.ResponseWriter, r *http.Request) {
	args, err := parseArgs(r)
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte(err.Error()))
		return
	}

	ctx := context.WithValue(r.Context(), provider.HTTPRequest, r)

	tkn, redirect, err := a.Authentication.Callback(ctx, args)
	if err != nil {
		if errors.Is(err, provider.ErrUserDisabled) {
			http.Redirect(w, r, "/login?error=user_disabled", http.StatusFound)
			return
		}

		// TODO: Better error handling!
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(err.Error()))
		return
	}

	w.Header().Set("Authorization", "Bearer "+tkn)
	c := &http.Cookie{
		Name:    "authorization",
		Path:    "/",
		Value:   tkn,
		Expires: time.Now().Add(5 * time.Minute),
	}
	http.SetCookie(w, c)

	if redirect != "" {
		http.Redirect(w, r, redirect, http.StatusFound)
		return
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte(tkn))
}

func (a *AuthenticationServer) Providers(ctx context.Context) (*oasAuthentication.ProvidersResponse, error) {
	providers := []oasAuthentication.ProvidersResponseProvidersItem{}
	for _, p := range a.Authentication.Providers() {
		if p == provider.LocalString || p == provider.LDAPString {
			continue
		}

		var i oasAuthentication.ProvidersResponseProvidersItem
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
			Type: oasAuthentication.ErrorTypeMissingToken,
			Msg:  "missing JWT token",
		}, nil
	}

	if err := a.Authentication.Check(ctx, tkn); err != nil {
		if !errors.Is(err, token.ErrInvalidToken) || !errors.Is(err, token.ErrInvalidTokenType) {
			return nil, fmt.Errorf("check JWT: %w", err)
		}

		return &oasAuthentication.CheckForbidden{
			Type: oasAuthentication.ErrorTypeInvalidToken,
			Msg:  err.Error(),
		}, nil
	}

	return &oasAuthentication.CheckResponse{}, nil
}

func (a *AuthenticationServer) AcknowledgeDisclaimer(ctx context.Context, req *oasAuthentication.AcknowledgeDisclaimerRequest) (oasAuthentication.AcknowledgeDisclaimerRes, error) {
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.AcknowledgeDisclaimerUnauthorized{
			Type: oasAuthentication.ErrorTypeMissingToken,
			Msg:  "missing JWT token",
		}, nil
	}

	if err := a.Authentication.AcknowledgeDisclaimer(ctx, tkn); err != nil {
		if !errors.Is(err, token.ErrInvalidToken) || !errors.Is(err, token.ErrInvalidTokenType) {
			return nil, fmt.Errorf("acknowledge disclaimer: %w", err)
		}

		return &oasAuthentication.AcknowledgeDisclaimerForbidden{
			Type: oasAuthentication.ErrorTypeInvalidToken,
			Msg:  err.Error(),
		}, nil
	}

	return &oasAuthentication.AcknowledgeDisclaimerResponse{}, nil
}

func (a *AuthenticationServer) VerifyEmail(ctx context.Context, req *oasAuthentication.VerifyEmailRequest) (oasAuthentication.VerifyEmailRes, error) {
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.VerifyEmailUnauthorized{
			Type: oasAuthentication.ErrorTypeMissingToken,
			Msg:  "missing JWT token",
		}, nil
	}

	if err := a.Authentication.VerifyEmail(ctx, tkn); err != nil {
		if !errors.Is(err, token.ErrInvalidToken) || !errors.Is(err, token.ErrInvalidTokenType) {
			return nil, fmt.Errorf("verify email: %w", err)
		}

		return &oasAuthentication.VerifyEmailForbidden{
			Type: oasAuthentication.ErrorTypeInvalidToken,
			Msg:  err.Error(),
		}, nil
	}

	return &oasAuthentication.VerifyEmailResponse{}, nil
}

func (a *AuthenticationServer) ResetPassword(ctx context.Context, req *oasAuthentication.ResetPasswordRequest) (oasAuthentication.ResetPasswordRes, error) {
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.ResetPasswordUnauthorized{
			Type: oasAuthentication.ErrorTypeMissingToken,
			Msg:  "missing JWT token",
		}, nil
	}

	if err := a.Authentication.ResetPassword(ctx, tkn, req.Password); err != nil {
		var apiErr isardvdi.Err
		if !errors.As(err, &apiErr) {
			return nil, err
		}

		// TODO: Handle API error correctly!
		return nil, apiErr
	}

	return &oasAuthentication.ResetPasswordResponse{}, nil
}

func (a *AuthenticationServer) ForgotPassword(ctx context.Context, req *oasAuthentication.ForgotPasswordRequest) (oasAuthentication.ForgotPasswordRes, error) {
	if err := a.Authentication.ForgotPassword(ctx, req.CategoryID, req.Email); err != nil {
		if !errors.Is(err, token.ErrInvalidToken) || !errors.Is(err, token.ErrInvalidTokenType) {
			return nil, fmt.Errorf("forgot password: %w", err)
		}

		return &oasAuthentication.ForgotPasswordForbidden{
			Type: oasAuthentication.ErrorTypeInvalidToken,
			Msg:  err.Error(),
		}, nil
	}

	return &oasAuthentication.ForgotPasswordResponse{}, nil
}
