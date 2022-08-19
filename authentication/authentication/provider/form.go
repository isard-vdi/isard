package provider

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

const FormString = "form"

type Form struct {
	cfg       cfg.Authentication
	providers map[string]Provider
}

func InitForm(cfg cfg.Authentication, db r.QueryExecutor) *Form {
	providers := map[string]Provider{}

	if cfg.Local.Enabled {
		local := InitLocal(db)
		providers[local.String()] = local
	}

	if cfg.LDAP.Enabled {
		ldap := InitLDAP(cfg.LDAP)
		providers[ldap.String()] = ldap
	}

	return &Form{
		cfg:       cfg,
		providers: providers,
	}
}

func (f *Form) Login(ctx context.Context, categoryID string, args map[string]string) (*model.User, string, error) {
	invCreds := false

	if f.cfg.Local.Enabled {
		u, redirect, err := f.providers[LocalString].Login(ctx, categoryID, args)
		if err == nil {
			return u, redirect, err
		}

		if !errors.Is(err, ErrInvalidCredentials) {
			return u, redirect, err
		}

		invCreds = true
	}

	if f.cfg.LDAP.Enabled {
		u, redirect, err := f.providers[LDAPString].Login(ctx, categoryID, args)
		if !errors.Is(err, ErrInvalidCredentials) {
			return u, redirect, err
		}

		invCreds = true
	}

	if invCreds {
		return nil, "", ErrInvalidCredentials
	}

	return nil, "", ErrUnknownIDP
}

func (f *Form) Callback(context.Context, *CallbackClaims, map[string]string) (*model.User, string, error) {
	return nil, "", errInvalidIDP
}

func (f *Form) AutoRegister() bool {
	for _, p := range f.providers {
		if p.AutoRegister() {
			return true
		}
	}

	return false
}

func (f *Form) String() string {
	return FormString
}

func (f *Form) Providers() []string {
	providers := []string{}
	for k := range f.providers {
		providers = append(providers, k)
	}

	return providers
}
