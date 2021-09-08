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
	m.HandleFunc("/config", a.config)

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

	tkn := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")

	if tkn == "" {
		if err := requiredArgs([]string{provider.ProviderArgsKey, provider.CategoryIDArgsKey}, args); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte(err.Error()))
			return
		}
	}

	args[provider.TokenArgsKey] = tkn
	prv := args[provider.ProviderArgsKey]
	cID := args[provider.CategoryIDArgsKey]

	tkn, redirect, err := a.Authentication.Login(r.Context(), prv, cID, args)
	if err != nil {
		if errors.Is(err, provider.ErrInvalidCredentials) {
			w.WriteHeader(http.StatusUnauthorized)
			w.Write([]byte(err.Error()))
			return
		}

		// TODO: Better error handling!
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(err.Error()))
		return
	}

	w.Header().Set("Authorization", "Bearer "+tkn)

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

	tkn, redirect, err := a.Authentication.Callback(r.Context(), args)
	if err != nil {
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
	UserShowAdminButton string `json:"user_show_admin_button"`
}

func (a *AuthenticationServer) config(w http.ResponseWriter, r *http.Request) {
	cfg := &configJSON{
		Providers: a.Authentication.Providers(),
		UserShowAdminButton: a.Authentication.UserShowAdminButton(),
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
