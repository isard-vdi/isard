package provider

import (
	"bytes"
	"encoding/base64"
	"encoding/gob"
	"fmt"
	"net/http"

	"github.com/isard-vdi/isard/backend/env"
	"github.com/isard-vdi/isard/backend/model"

	"github.com/segmentio/ksuid"
	"golang.org/x/oauth2"
)

const (
	oauth2StateKey = "state"
	oauth2CodeKey  = "code"
)

func init() {
	gob.Register(&oauth2.Token{})
	gob.Register(&oauth2Info{})
}

type oauth2Provider interface {
	Provider

	cfg(env *env.Env) *oauth2.Config
}

type oauth2Info struct {
	State,
	Category,
	Redirect string
}

func oauth2Login(env *env.Env, p oauth2Provider, w http.ResponseWriter, r *http.Request) {
	info := &oauth2Info{
		State:    ksuid.New().String(),
		Category: r.URL.Query().Get(CategoryKey),
		Redirect: r.URL.Query().Get(redirectKey),
	}

	sess, err := env.Auth.SessStore.New(r, info.State)
	if err != nil {
		http.Error(w, fmt.Sprintf("create session: %v", err), http.StatusInternalServerError)
		return
	}

	sess.Options.MaxAge = 60 * 10 // 10 mins
	sess.Values[ProviderStoreKey] = p.String()

	if err := sess.Save(r, w); err != nil {
		http.Error(w, fmt.Sprintf("save session: %v", err), http.StatusInternalServerError)
		return
	}

	buf := bytes.NewBuffer(nil)
	if err := gob.NewEncoder(buf).Encode(info); err != nil {
		http.Error(w, fmt.Sprintf("encode oauth2 info: %v", err), http.StatusInternalServerError)
		return
	}

	enc := base64.StdEncoding.EncodeToString(buf.Bytes())

	http.Redirect(w, r, p.cfg(env).AuthCodeURL(enc), http.StatusFound)
}

func oauth2Callback(env *env.Env, w http.ResponseWriter, r *http.Request) {
	oauth2State := r.FormValue(oauth2StateKey)

	b, err := base64.StdEncoding.DecodeString(oauth2State)
	if err != nil {
		http.Error(w, "invalid state", http.StatusBadRequest)
		return
	}

	info := &oauth2Info{}
	gob.NewDecoder(bytes.NewBuffer(b)).Decode(info)

	q := r.URL.Query()
	q.Add(CategoryKey, info.Category)
	q.Add(redirectKey, info.Redirect)
	r.URL.RawQuery = q.Encode()

	state, err := env.Auth.SessStore.Get(r, info.State)
	if err != nil {
		http.Error(w, fmt.Sprintf("get state session: %v", err), http.StatusInternalServerError)
		return
	}

	prov, ok := state.Values[ProviderStoreKey].(string)
	if !ok {
		http.Error(w, "invalid state", http.StatusBadRequest)
		return
	}

	p := FromString(prov).(oauth2Provider)

	// Remove the state session
	state.Options.MaxAge = -1
	if err := state.Save(r, w); err != nil {
		http.Error(w, fmt.Sprintf("delete session: %v", err), http.StatusInternalServerError)
		return
	}

	tkn, err := p.cfg(env).Exchange(r.Context(), r.FormValue(oauth2CodeKey))
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	u := &model.User{Category: getCategory(r)}
	if err := p.Get(env, u, tkn); err != nil {
		http.Error(w, fmt.Sprintf("get user from idp: %v", err), http.StatusInternalServerError)
		return
	}

	oauth2NewSession(env, w, r, p, u, tkn)
}

func oauth2NewSession(env *env.Env, w http.ResponseWriter, r *http.Request, p Provider, u *model.User, val interface{}) {
	if err := autoRegistration(env, u, w, r); err != nil {
		autoRegistrationCookie(env, w, r, p, u, val)
		return
	}

	sess, err := env.Auth.SessStore.New(r, SessionStoreKey)
	if err != nil {
		http.Error(w, fmt.Sprintf("create session: %v", err), http.StatusInternalServerError)
		return
	}

	sess.Values[ProviderStoreKey] = p.String()
	sess.Values[IDStoreKey] = u.ID()
	sess.Values[ValueStoreKey] = val

	if err := sess.Save(r, w); err != nil {
		http.Error(w, fmt.Sprintf("save session: %v", err), http.StatusInternalServerError)
		return
	}

	redirect(w, r)
}
