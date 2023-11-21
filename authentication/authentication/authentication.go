package authentication

import (
	"context"
	"errors"
	"fmt"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/crewjam/saml/samlsp"
	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

const adminUsr = "local-default-admin-admin"

type Interface interface {
	Providers() []string
	Provider(provider string) provider.Provider

	Login(ctx context.Context, provider string, categoryID string, args map[string]string) (tkn, redirect string, err error)
	Callback(ctx context.Context, args map[string]string) (tkn, redirect string, err error)
	Check(ctx context.Context, tkn string) error

	RequestEmailValidation(ctx context.Context, tkn string, email string) error
	ValidateEmail(ctx context.Context, tkn string) error

	SAML() *samlsp.Middleware
	// Refresh()
	// Register()
}

type Authentication struct {
	Log       *zerolog.Logger
	Secret    string
	Duration  time.Duration
	DB        r.QueryExecutor
	providers map[string]provider.Provider
	saml      *samlsp.Middleware
}

func Init(cfg cfg.Cfg, log *zerolog.Logger, db r.QueryExecutor) *Authentication {
	a := &Authentication{
		Log:      log,
		Secret:   cfg.Authentication.Secret,
		Duration: cfg.Authentication.TokenDuration,
		DB:       db,
	}

	providers := map[string]provider.Provider{
		provider.UnknownString:  &provider.Unknown{},
		provider.FormString:     provider.InitForm(cfg.Authentication, db),
		provider.ExternalString: &provider.External{},
	}

	if cfg.Authentication.SAML.Enabled {
		saml := provider.InitSAML(cfg.Authentication)
		a.saml = saml.Middleware
		providers[saml.String()] = saml
	}

	if cfg.Authentication.Google.Enabled {
		google := provider.InitGoogle(cfg.Authentication)
		providers[google.String()] = google
	}

	a.providers = providers

	return a
}

func (a *Authentication) Providers() []string {
	providers := []string{}
	for k, v := range a.providers {
		if k == provider.UnknownString || k == provider.ExternalString {
			continue
		}

		if k == provider.FormString {
			providers = append(providers, v.(*provider.Form).Providers()...)
			continue
		}

		providers = append(providers, k)
	}

	return providers
}

func (a *Authentication) Provider(p string) provider.Provider {
	prv := a.providers[p]
	if prv == nil {
		return a.providers[provider.UnknownString]
	}

	return prv
}

func (a *Authentication) Login(ctx context.Context, prv, categoryID string, args map[string]string) (string, string, error) {
	// Check if the user sends a token
	if args[provider.TokenArgsKey] != "" {
		tkn, tknType, err := token.VerifyToken(a.DB, a.Secret, args[provider.TokenArgsKey])
		if err != nil {
			return "", "", fmt.Errorf("verify the JWT token: %w", err)
		}

		switch tknType {
		case token.TypeRegister:
			register := tkn.Claims.(*token.RegisterClaims)

			u := &model.User{
				Provider: register.Provider,
				Category: register.CategoryID,
				UID:      register.UserID,
			}
			if err := u.LoadWithoutID(ctx, a.DB); err != nil {
				if errors.Is(err, db.ErrNotFound) {
					return "", "", errors.New("user not registered")
				}

				return "", "", fmt.Errorf("load user from db: %w", err)
			}

			ss, err := token.SignLoginToken(a.Secret, a.Duration, u)
			if err != nil {
				return "", "", err
			}

			a.Log.Info().Str("usr", u.ID).Str("tkn", ss).Msg("register succeeded")

			return ss, args[provider.RedirectArgsKey], nil

		case token.TypeExternal:
			claims := tkn.Claims.(*token.ExternalClaims)

			args["category_id"] = claims.CategoryID
			args["external_app_id"] = claims.KeyID
			args["external_group_id"] = claims.GroupID
			args["user_id"] = claims.UserID
			args["username"] = claims.Username
			args["kid"] = claims.KeyID
			args["role"] = claims.Role
			args["name"] = claims.Name
			args["email"] = claims.Email
			args["photo"] = claims.Photo
		}

	} else {
		// There are some login providers that require a token
		if prv == provider.ExternalString {
			return "", "", errors.New("missing JWT token")
		}
	}

	p := a.Provider(prv)
	g, u, redirect, err := p.Login(ctx, categoryID, args)
	if err != nil {
		a.Log.Info().Str("prv", p.String()).Err(err).Msg("login failed")

		return "", "", fmt.Errorf("login: %w", err)
	}

	if redirect != "" {
		return "", redirect, nil
	}

	normalizeIdentity(g, u)

	uExists, err := u.Exists(ctx, a.DB)
	if err != nil {
		return "", "", fmt.Errorf("check if user exists: %w", err)
	}

	if !uExists {
		// Manual registration
		if !p.AutoRegister() {
			// If the user has logged in correctly, but doesn't exist in the DB, they have to register first!
			ss, err := token.SignRegisterToken(a.Secret, a.Duration, u)

			a.Log.Info().Err(err).Str("usr", u.UID).Str("tkn", ss).Msg("register token signed")

			return ss, "", err
		}

		// Automatic group registration!
		gExists, err := g.Exists(ctx, a.DB)
		if err != nil {
			return "", "", fmt.Errorf("check if group exists: %w", err)
		}

		if !gExists {
			if err := a.registerGroup(g); err != nil {
				return "", "", fmt.Errorf("auto register group: %w", err)
			}
		}

		// Set the user group to the new group created
		u.Group = g.ID

		// Automatic registration!
		if err := a.registerUser(u); err != nil {
			return "", "", fmt.Errorf("auto register user: %w", err)
		}
	}

	return a.finishLogin(ctx, u, args[provider.RedirectArgsKey])
}

func (a *Authentication) Callback(ctx context.Context, args map[string]string) (string, string, error) {
	ss := args["state"]
	if ss == "" {
		return "", "", errors.New("callback state not provided")
	}

	tkn, err := token.ParseAuthenticationToken(a.Secret, ss, &token.CallbackClaims{})
	if err != nil {
		return "", "", fmt.Errorf("parse callback state: %w", err)
	}

	claims, ok := tkn.Claims.(*token.CallbackClaims)
	if !ok {
		return "", "", errors.New("unknown callback state claims format")
	}

	p := a.Provider(claims.Provider)

	// TODO: Add autoregister for more providers?
	_, u, redirect, err := p.Callback(ctx, claims, args)
	if err != nil {
		return "", "", fmt.Errorf("callback: %w", err)
	}

	exists, err := u.Exists(ctx, a.DB)
	if err != nil {
		return "", "", fmt.Errorf("check if user exists: %w", err)
	}

	if redirect == "" {
		redirect = claims.Redirect
	}

	if !exists {
		ss, err = token.SignRegisterToken(a.Secret, a.Duration, u)
		if err != nil {
			return "", "", err
		}

		a.Log.Info().Str("usr", u.UID).Str("tkn", ss).Msg("register token signed")

		return ss, redirect, nil
	}

	return a.finishLogin(ctx, u, redirect)
}

func (a *Authentication) finishLogin(ctx context.Context, u *model.User, redirect string) (string, string, error) {
	// Check if the user is disabled
	if !u.Active {
		return "", "", provider.ErrUserDisabled
	}

	// // Check if the user has the email verified
	// const validateEmail = true // TODO: This needs to be at the cfg
	// if validateEmail && !u.EmailVerified {
	// 	token.SignCallbackToken(secret string, prv string, cat string, redirect string)
	// }

	u.Accessed = float64(time.Now().Unix())

	u2 := &model.User{ID: u.ID}
	if err := u2.Load(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("load user from DB: %w", err)
	}

	u.LoadWithoutOverride(u2)
	if err := u.Update(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("update user in the DB: %w", err)
	}

	normalizeIdentity(nil, u)

	ss, err := token.SignLoginToken(a.Secret, a.Duration, u)
	if err != nil {
		return "", "", err
	}

	a.Log.Info().Str("usr", u.ID).Str("tkn", ss).Str("redirect", redirect).Msg("login succeeded")

	return ss, redirect, nil
}

func (a *Authentication) Check(ctx context.Context, ss string) error {
	tkn, err := token.ParseAuthenticationToken(a.Secret, ss, &token.LoginClaims{})
	if err != nil {
		return err
	}

	_, ok := tkn.Claims.(*token.LoginClaims)
	if !ok {
		return errors.New("unknown JWT claims format")
	}

	return nil
}

func (a *Authentication) SAML() *samlsp.Middleware {
	return a.saml
}
