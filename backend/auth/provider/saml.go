package provider

import (
	"context"
	"crypto/rsa"
	"crypto/tls"
	"encoding/gob"
	"fmt"
	"net/http"
	"net/url"

	"github.com/isard-vdi/isard/backend/env"
	"github.com/isard-vdi/isard/backend/model"

	"github.com/crewjam/saml"
	"github.com/crewjam/saml/samlsp"
	"github.com/nefixestrada/pongo"
	"github.com/spf13/afero"
)

const provSAML = "saml"

func init() {
	gob.Register(&SAML{})
	gob.Register(samlsp.Attributes{})
}

type SAML struct{}

func NewSAMLProvider(env *env.Env) (*samlsp.Middleware, error) {
	pair, err := loadKeyPair(env)
	if err != nil {
		return nil, err
	}

	metadata, err := loadIDPMetadata(env)
	if err != nil {
		return nil, err
	}

	callbackURL, err := url.Parse(env.Cfg.Auth.SAML.Callback)
	if err != nil {
		return nil, err
	}
	callbackURL = callbackURL.ResolveReference(&url.URL{Path: "/callback/saml"})

	m, err := pongo.New(env.Auth.SessStore, samlsp.Options{
		URL:         *callbackURL,
		Key:         pair.PrivateKey.(*rsa.PrivateKey),
		Certificate: pair.Leaf,
		IDPMetadata: metadata,
	})
	if err != nil {
		return nil, fmt.Errorf("create SAML middleware: %w", err)
	}

	return m, nil
}

func (SAML) String() string {
	return provSAML
}

func (s SAML) Login(env *env.Env, w http.ResponseWriter, r *http.Request) {
	session, err := env.Auth.SAML.Session.GetSession(r)
	if err != nil {
		if err == samlsp.ErrNoSession {
			env.Auth.SAML.HandleStartAuthFlow(w, r)
		}

		http.Error(w, fmt.Sprintf("error getting the session: %v", err), http.StatusInternalServerError)
		return
	}

	attrs := session.(samlsp.SessionWithAttributes).GetAttributes()
	u := &model.User{Category: getCategory(r)}
	if err := s.Get(env, u, attrs); err != nil {
		http.Error(w, fmt.Sprintf("get user from idp: %v", err), http.StatusInternalServerError)
		return
	}

	s.NewSession(env, w, r, u, attrs)
}

func (s SAML) Callback(env *env.Env, w http.ResponseWriter, r *http.Request) {
	env.Auth.SAML.ServeHTTP(w, r)
}

func (s SAML) NewSession(env *env.Env, w http.ResponseWriter, r *http.Request, u *model.User, val interface{}) {
	if err := autoRegistration(env, u, w, r); err != nil {
		autoRegistrationCookie(env, w, r, s, u, val)

		return
	}

	sess, err := env.Auth.SessStore.New(r, SessionStoreKey)
	if err != nil {
		http.Error(w, fmt.Sprintf("create session: %v", err), http.StatusInternalServerError)
		return
	}

	sess.Values[ProviderStoreKey] = s.String()
	sess.Values[IDStoreKey] = u.ID()
	sess.Values[ValueStoreKey] = val

	if err := sess.Save(r, w); err != nil {
		http.Error(w, fmt.Sprintf("save session: %v", err), http.StatusInternalServerError)
		return
	}

	redirect(w, r)
}

func (s SAML) Get(env *env.Env, u *model.User, val interface{}) error {
	attrs := val.(samlsp.Attributes)

	u.UID = attrs.Get(env.Cfg.Auth.SAML.AttrID)
	if u.UID == "" {
		return fmt.Errorf("no id for the user was found. Please, contact the administrator")
	}

	u.Username = attrs.Get(env.Cfg.Auth.SAML.AttrUsername)
	if u.Username == "" {
		u.Username = u.UID
	}

	u.Provider = s.String()
	u.Name = attrs.Get(env.Cfg.Auth.SAML.AttrName)
	u.Email = attrs.Get(env.Cfg.Auth.SAML.AttrEmail)
	u.Photo = attrs.Get(env.Cfg.Auth.SAML.AttrPhoto)

	return nil
}

func loadKeyPair(env *env.Env) (tls.Certificate, error) {
	crt, err := afero.ReadFile(env.FS, env.Cfg.Auth.SAML.CertPath)
	if err != nil {
		return tls.Certificate{}, fmt.Errorf("read cert file: %w", err)
	}

	key, err := afero.ReadFile(env.FS, env.Cfg.Auth.SAML.KeyPath)
	if err != nil {
		return tls.Certificate{}, fmt.Errorf("read key file: %w", err)
	}

	pair, err := tls.X509KeyPair(crt, key)
	if err != nil {
		return tls.Certificate{}, fmt.Errorf("parse pair: %w", err)
	}

	return pair, nil
}

func loadIDPMetadata(env *env.Env) (*saml.EntityDescriptor, error) {
	if env.Cfg.Auth.SAML.IdpMetadataPath != "" {
		b, err := afero.ReadFile(env.FS, env.Cfg.Auth.SAML.IdpMetadataPath)
		if err != nil {
			return nil, fmt.Errorf("read idp metadata file: %w", err)
		}

		m, err := samlsp.ParseMetadata(b)
		if err != nil {
			return nil, fmt.Errorf("parse idp metadata: %w", err)
		}

		return m, nil
	}

	url, err := url.Parse(env.Cfg.Auth.SAML.IdpMetadataURL)
	if err != nil {
		return nil, fmt.Errorf("parse idp metadata URL: %w", err)
	}

	m, err := samlsp.FetchMetadata(context.Background(), http.DefaultClient, *url)
	if err != nil {
		return nil, fmt.Errorf("fetch idp metadata: %w", err)
	}

	return m, nil
}
