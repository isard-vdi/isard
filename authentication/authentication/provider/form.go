package provider

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/authentication/limits"
	"gitlab.com/isard/isardvdi/authentication/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

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
		ldap := InitLDAP(cfg.LDAP)
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

type formArgs struct {
	Username string `json:"username,omitempty"`
	Password string `json:"password,omitempty"`
}

func parseFormArgs(args map[string]string) (string, string, error) {
	username := args["username"]
	password := args["password"]

	creds := &formArgs{}
	if body, ok := args[RequestBodyArgsKey]; ok && body != "" {
		if err := json.Unmarshal([]byte(body), creds); err != nil {
			return "", "", fmt.Errorf("unmarshal form authentication request body: %w", err)
		}
	}

	if username == "" {
		if creds.Username == "" {
			return "", "", errors.New("username not provided")
		}

		username = creds.Username
	}

	if password == "" {
		if creds.Password == "" {
			return "", "", errors.New("password not provided")
		}

		password = creds.Password
	}

	return username, password, nil
}

func (f *Form) Login(ctx context.Context, categoryID string, args map[string]string) (*model.Group, *model.User, string, *ProviderError) {
	usr, pwd, err := parseFormArgs(args)
	if err != nil {
		return nil, nil, "", &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}

	if f.limits != nil {
		// Check if the user is rate limited
		if err := f.limits.IsRateLimited(usr, categoryID, f.String()); err != nil {
			return nil, nil, "", &ProviderError{
				User:   errors.New("user is currently rate limited"),
				Detail: err,
			}
		}

	}

	args[FormUsernameArgsKey] = usr
	args[FormPasswordArgsKey] = pwd

	var invCreds *ProviderError

	if f.cfg.Local.Enabled {
		g, u, redirect, err := f.providers[types.Local].Login(ctx, categoryID, args)
		if err == nil {
			if f.limits != nil {
				// Clean the user rate limits record because the user has logged in correctly
				f.limits.CleanRateLimit(usr, categoryID, f.String())
			}

			return g, u, redirect, nil
		}

		if !errors.Is(err, ErrInvalidCredentials) {
			return g, u, redirect, err
		}

		invCreds = err
		invCreds.Detail = fmt.Errorf("local: %w", invCreds.Detail)
	}

	if f.cfg.LDAP.Enabled {
		g, u, redirect, err := f.providers[types.LDAP].Login(ctx, categoryID, args)
		// Clean the user rate limits record because the user has logged in correctly
		if err == nil {
			if f.limits != nil {
				f.limits.CleanRateLimit(usr, categoryID, f.String())
			}

			return g, u, redirect, nil
		}

		if !errors.Is(err, ErrInvalidCredentials) {
			return g, u, redirect, err
		}

		invCreds = err
		invCreds.Detail = fmt.Errorf("ldap: %w", invCreds.Detail)
	}

	if invCreds != nil {
		if f.limits != nil {
			// Record the failed attempt and return an error if the user has been rate limited
			if err := f.limits.RecordFailedAttempt(usr, categoryID, f.String()); err != nil {
				return nil, nil, "", &ProviderError{
					User:   errors.New("user is currently rate limited"),
					Detail: err,
				}
			}
		}

		return nil, nil, "", invCreds
	}

	return nil, nil, "", &ProviderError{
		User:   ErrUnknownIDP,
		Detail: errors.New("no active provider was found for the form login"),
	}
}

func (f *Form) Callback(context.Context, *token.CallbackClaims, map[string]string) (*model.Group, *model.User, string, *ProviderError) {
	return nil, nil, "", &ProviderError{
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
	return types.Form
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
