package http

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/authentication/provider"

	"github.com/crewjam/saml/samlsp"
	"github.com/rs/zerolog"
)

type AuthenticationServer struct {
	Addr           string
	Authentication authentication.Interface

	Log *zerolog.Logger
	WG  *sync.WaitGroup
}

func (a *AuthenticationServer) Serve(ctx context.Context) {
	m := http.NewServeMux()
	m.HandleFunc("/login", a.login)
	m.HandleFunc("/callback", a.callback)
	m.HandleFunc("/check", a.check)
	m.HandleFunc("/providers", a.providers)

	// SAML authentication
	m.HandleFunc("/saml/metadata", a.Authentication.SAML().ServeMetadata)
	m.HandleFunc("/saml/acs", a.Authentication.SAML().ServeACS)

	s := http.Server{
		Addr:    a.Addr,
		Handler: m,
	}

	go func() {
		if err := s.ListenAndServe(); err != nil {
			a.Log.Fatal().Err(err).Str("addr", a.Addr).Msg("serve http")
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

func (a *AuthenticationServer) check(w http.ResponseWriter, r *http.Request) {
	tkn := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if tkn == "" {
		w.WriteHeader(http.StatusUnauthorized)
		w.Write([]byte("invalid token"))
		return
	}

	if err := a.Authentication.Check(r.Context(), tkn); err != nil {
		// TODO: Better error handling!
		w.WriteHeader(http.StatusUnauthorized)
		w.Write([]byte(err.Error()))
		return
	}

	w.WriteHeader(http.StatusOK)
}

type configJSON struct {
	Providers []string `json:"providers"`
}

func (a *AuthenticationServer) providers(w http.ResponseWriter, r *http.Request) {
	providers := []string{}
	for _, p := range a.Authentication.Providers() {
		if p == provider.LocalString || p == provider.LDAPString {
			continue
		}

		providers = append(providers, p)
	}

	cfg := &configJSON{
		Providers: providers,
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)

	enc := json.NewEncoder(w)
	enc.SetIndent("", "    ")
	if err := enc.Encode(cfg); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(fmt.Errorf("encode response: %w", err).Error()))
		return
	}
}
