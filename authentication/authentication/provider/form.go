package provider

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

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

func (f *Form) Login(ctx context.Context, categoryID string, args map[string]string) (*model.Group, *model.User, string, error) {
	invCreds := false

	if f.cfg.Local.Enabled {
		g, u, redirect, err := f.providers[types.Local].Login(ctx, categoryID, args)
		if err == nil {
			return g, u, redirect, err
		}

		if !errors.Is(err, ErrInvalidCredentials) {
			return g, u, redirect, err
		}

		invCreds = true
	}

	if f.cfg.LDAP.Enabled {
		g, u, redirect, err := f.providers[types.LDAP].Login(ctx, categoryID, args)
		if !errors.Is(err, ErrInvalidCredentials) {
			return g, u, redirect, err
		}

		invCreds = true
	}

	if invCreds {
		return nil, nil, "", ErrInvalidCredentials
	}

	return nil, nil, "", ErrUnknownIDP
}

func (f *Form) Callback(context.Context, *token.CallbackClaims, map[string]string) (*model.Group, *model.User, string, error) {
	return nil, nil, "", errInvalidIDP
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
	return types.Form
}

func (f *Form) Providers() []string {
	providers := []string{}
	for k := range f.providers {
		providers = append(providers, k)
	}

	return providers
}
