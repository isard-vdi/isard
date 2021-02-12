package provider

import (
	"errors"
	"fmt"
	"net/http"

	"github.com/isard-vdi/isard/backend/env"
	"github.com/isard-vdi/isard/backend/model"
	"github.com/isard-vdi/isard/backend/pkg/utils"
)

const provLocal = "local"

const (
	userKey = "usr"
	passwordKey = "pwd"
)


type Local struct{}

func (Local) String() string {
	return provLocal
}

func (l Local) Login(env *env.Env, w http.ResponseWriter, r *http.Request) {
	usr := r.FormValue(userKey)
	if usr == "" {
		http.Error(w, "no user was provided", http.StatusBadRequest)
		return
	}

	pwd := r.FormValue(passwordKey)
	if pwd == "" {
		http.Error(w, "no password was provided", http.StatusBadRequest)
		return
	}

	u := &model.User{
		Provider: l.String(),
		UID:      usr,
		Username: usr,
		Category: getCategory(r),
	}

	if err := env.Isard.Login(u, pwd); err != nil {
		var e *utils.ErrHTTPCode
		if errors.As(err, &e) {
			if e.Code == http.StatusForbidden {
				w.WriteHeader(http.StatusForbidden)
				w.Write([]byte(`<h1>Incorrect login credentials</h1><a href="/">Go back</a>`))
				return
			}
		}

		http.Error(w, err.Error(), http.StatusForbidden)
		return
	}

	if err := l.Get(env, u, nil); err != nil {
		http.Error(w, fmt.Sprintf("get user from idp: %v", err), http.StatusInternalServerError)
		return
	}

	l.NewSession(env, w, r, u, nil)
}

func (l Local) Callback(env *env.Env, w http.ResponseWriter, r *http.Request) {
	redirect(w, r)
}

func (l Local) NewSession(env *env.Env, w http.ResponseWriter, r *http.Request, u *model.User, val interface{}) {
	if err := autoRegistration(env, u, w, r); err != nil {
		if errors.Is(err, ErrNoAutoRegistrationKey) {
			autoRegistrationCookie(env, w, r, l, u, val)
			return
		}

		http.Error(w, fmt.Sprintf("create session: %v", err), http.StatusInternalServerError)
	}

	sess, err := env.Auth.SessStore.New(r, SessionStoreKey)
	if err != nil {
		http.Error(w, fmt.Sprintf("create session: %v", err), http.StatusInternalServerError)
		return
	}

	sess.Values[ProviderStoreKey] = l.String()
	sess.Values[IDStoreKey] = u.ID()

	if err := sess.Save(r, w); err != nil {
		http.Error(w, fmt.Sprintf("save session: %v", err), http.StatusInternalServerError)
		return
	}

	redirect(w, r)
}

func (l Local) Get(env *env.Env, u *model.User, val interface{}) error {
	return nil
}
