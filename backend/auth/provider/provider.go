package provider

import (
	"bytes"
	"encoding/base64"
	"encoding/gob"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/gorilla/mux"
	"github.com/isard-vdi/isard/backend/env"
	"github.com/isard-vdi/isard/backend/model"
)

const (
	SessionStoreKey           = "session"
	ProviderStoreKey          = "provider"
	IDStoreKey                = "id"
	ValueStoreKey             = "value"
	redirectKey               = "redirect"
	registerKey               = "code"
	CategoryKey               = "category"
	AutoRegistrationCookieKey = "autoregistration"
)

var (
	ErrNoAutoRegistrationKey = errors.New("no autoregistration key was provided")
)

func init() {
	gob.Register(&AutoRegistrationCookieStruct{})
}

type Provider interface {
	// TODO: Context
	Get(env *env.Env, u *model.User, val interface{}) error
	Login(env *env.Env, w http.ResponseWriter, r *http.Request)
	Callback(env *env.Env, w http.ResponseWriter, r *http.Request)
	NewSession(env *env.Env, w http.ResponseWriter, r *http.Request, u *model.User, val interface{})
	String() string
}

func FromString(p string) Provider {
	switch p {
	case provLocal:
		return &Local{}
	case provGitHub:
		return &GitHub{}
	case provSAML:
		return &SAML{}
	case provGoogle:
		return &Google{}
	default:
		return &Unknown{}
	}
}

func Callback(env *env.Env, w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	prov, ok := vars["provider"]
	if !ok {
		http.Error(w, "unknown identity provider", http.StatusBadRequest)
		return
	}

	p := FromString(prov)
	if p.String() == "unknown" {
		http.Error(w, "unknown identity provider", http.StatusBadRequest)
		return
	}

	p.Callback(env, w, r)
}

func autoRegistration(env *env.Env, u *model.User, w http.ResponseWriter, r *http.Request) error {
	if err := env.Isard.UserLoad(u); err != nil {
		if errors.Is(err, model.ErrNotFound) {
			if env.Cfg.Auth.AutoRegistration {
				code := r.FormValue(registerKey)
				if code == "" {
					return ErrNoAutoRegistrationKey
				}

				if err := env.Isard.CheckRegistrationCode(u, code); err != nil {
					return fmt.Errorf("autoregister user: %w", err)
				}

				// TODO: Local users don't have their provider updated
				if err := env.Isard.UserRegister(u); err != nil {
					return fmt.Errorf("autoregister user: %w", err)
				}

				return nil
			}

			env.Sugar.Warnf("user %s tried to autoregistrate", u.ID)

			err = errors.New("user not found and autoregistration disabled. If you think you should be able to use the service, please contact the administrator")
			http.Error(w, err.Error(), http.StatusForbidden)
			return err
		}

		http.Error(w, err.Error(), http.StatusInternalServerError)
		return err
	}

	return nil
}

func autoRegistrationCookie(env *env.Env, w http.ResponseWriter, r *http.Request, p Provider, u *model.User, val interface{}) {
	cVal := &AutoRegistrationCookieStruct{
		Provider: p,
		User:     u,
		Val:      val,
	}

	buf := bytes.NewBuffer(nil)
	if err := gob.NewEncoder(buf).Encode(cVal); err != nil {
		// This should panic, since it's a coding related issue
		env.Sugar.Panicf("encode autoregistration cookie: %v", err)
	}

	c := &http.Cookie{
		Name:  AutoRegistrationCookieKey,
		Value: base64.StdEncoding.EncodeToString(buf.Bytes()),

		Path:     "/api/",
		Domain:   env.Cfg.BackendHost,
		MaxAge:   int(24 * time.Hour.Seconds()),
		SameSite: http.SameSiteStrictMode,
	}

	url := "/register"
	redirect := r.URL.Query().Get(redirectKey)
	if redirect != "" {
		url = fmt.Sprintf("/register?%s=%s", redirectKey, redirect)
	}

	http.SetCookie(w, c)
	http.Redirect(w, r, url, http.StatusFound)
}

type AutoRegistrationCookieStruct struct {
	Provider Provider
	User     *model.User
	Val      interface{}
}

func redirect(w http.ResponseWriter, r *http.Request) {
	r.URL.Path = "/api/v2/check"

	http.Redirect(w, r, r.URL.String(), http.StatusFound)
}

func getCategory(r *http.Request) string {
	category := r.URL.Query().Get(CategoryKey)
	if category == "" {
		category = "default"
	}

	return category
}

type Unknown struct{}

func (Unknown) String() string {
	return "unknown"
}

func (Unknown) Login(env *env.Env, w http.ResponseWriter, r *http.Request) {
	http.Error(w, "unknown identity provider", http.StatusBadRequest)
}

func (Unknown) Callback(env *env.Env, w http.ResponseWriter, r *http.Request) {
	http.Error(w, "unknown identity provider", http.StatusBadRequest)
}

func (Unknown) NewSession(env *env.Env, w http.ResponseWriter, r *http.Request, u *model.User, val interface{}) {
	http.Error(w, "unknown identity provider", http.StatusBadRequest)
}

func (Unknown) Get(env *env.Env, u *model.User, val interface{}) error {
	return fmt.Errorf("unknown identity provider")
}
