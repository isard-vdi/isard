package provider

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/limits"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var _ Provider = &Form{}

type Form struct {
	cfg       cfg.Authentication
	providers map[string]Provider
	limits    *limits.Limits
}

func InitForm(cfg cfg.Authentication, db r.QueryExecutor) *Form {
	providers := map[string]Provider{}

	if cfg.Local.Enabled {
		local := InitLocal(db)
		providers[local.String()] = local
	}

	if cfg.LDAP.Enabled {
		ldap := InitLDAP(cfg.LDAP, cfg.Secret, db)
		providers[ldap.String()] = ldap
	}

	f := &Form{
		cfg:       cfg,
		providers: providers,
	}

	if cfg.Limits.Enabled {
		f.limits = limits.NewLimits(cfg.Limits.MaxAttempts, cfg.Limits.RetryAfter, cfg.Limits.IncrementFactor, cfg.Limits.MaxTime)
	}

	return f
}

func formCheckRequiredArgs(args LoginArgs) error {
	if args.FormUsername == nil {
		return errors.New("username not provided")
	}

	if args.FormPassword == nil {
		return errors.New("password not provided")
	}

	return nil
}

func (f *Form) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	if err := formCheckRequiredArgs(args); err != nil {
		return nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}

	if f.limits != nil {
		// Check if the user is rate limited
		if err := f.limits.IsRateLimited(*args.FormUsername, categoryID, f.String()); err != nil {
			return nil, nil, "", "", &ProviderError{
				User:   errors.New("user is currently rate limited"),
				Detail: err,
			}
		}

	}

	var invCreds *ProviderError

	if f.cfg.Local.Enabled {
		g, u, redirect, ss, err := f.providers[types.ProviderLocal].Login(ctx, categoryID, args)
		if err == nil {
			if f.limits != nil {
				// Clean the user rate limits record because the user has logged in correctly
				f.limits.CleanRateLimit(*args.FormUsername, categoryID, f.String())
			}

			return g, u, redirect, ss, nil
		}

		if !errors.Is(err, ErrInvalidCredentials) {
			return g, u, redirect, ss, err
		}

		invCreds = err
		invCreds.Detail = fmt.Errorf("local: %w", invCreds.Detail)
	}

	if f.cfg.LDAP.Enabled {
		g, u, redirect, ss, err := f.providers[types.ProviderLDAP].Login(ctx, categoryID, args)
		// Clean the user rate limits record because the user has logged in correctly
		if err == nil {
			if f.limits != nil {
				f.limits.CleanRateLimit(*args.FormUsername, categoryID, f.String())
			}

			return g, u, redirect, ss, nil
		}

		if !errors.Is(err, ErrInvalidCredentials) {
			return g, u, redirect, ss, err
		}

		invCreds = err
		invCreds.Detail = fmt.Errorf("ldap: %w", invCreds.Detail)
	}

	if invCreds != nil {
		if f.limits != nil {
			// Record the failed attempt and return an error if the user has been rate limited
			if err := f.limits.RecordFailedAttempt(*args.FormUsername, categoryID, f.String()); err != nil {
				return nil, nil, "", "", &ProviderError{
					User:   errors.New("user is currently rate limited"),
					Detail: err,
				}
			}
		}

		return nil, nil, "", "", invCreds
	}

	return nil, nil, "", "", &ProviderError{
		User:   ErrUnknownIDP,
		Detail: errors.New("no active provider was found for the form login"),
	}
}

func (f *Form) Callback(context.Context, *token.CallbackClaims, CallbackArgs) (*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	return nil, nil, "", "", &ProviderError{
		User:   errInvalidIDP,
		Detail: errors.New("the local provider doesn't support the callback operation"),
	}
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
	return types.ProviderForm
}

func (f *Form) Providers() []string {
	providers := []string{}
	for k := range f.providers {
		providers = append(providers, k)
	}

	return providers
}

func (f *Form) Healthcheck() error {
	for _, p := range f.providers {
		if err := p.Healthcheck(); err != nil {
			return fmt.Errorf("error in provider '%s': %w ", p.String(), err)
		}
	}

	return nil
}
