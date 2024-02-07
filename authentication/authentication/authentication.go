package authentication

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/pkg/db"
	"gitlab.com/isard/isardvdi/pkg/gen/oas/notifier"
	"gitlab.com/isard/isardvdi/pkg/http"
	"gitlab.com/isard/isardvdi/pkg/jwt"

	"github.com/crewjam/saml/samlsp"
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-sdk-go"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Interface interface {
	Providers() []string
	Provider(provider string) provider.Provider

	Login(ctx context.Context, provider string, categoryID string, args map[string]string) (tkn, redirect string, err error)
	Callback(ctx context.Context, ss string, args map[string]string) (tkn, redirect string, err error)
	Check(ctx context.Context, tkn string) error

	AcknowledgeDisclaimer(ctx context.Context, tkn string) error
	RequestEmailVerification(ctx context.Context, tkn string, email string) error
	VerifyEmail(ctx context.Context, tkn string) error
	ForgotPassword(ctx context.Context, categoryID, email string) error
	ResetPassword(ctx context.Context, tkn string, pwd string) error

	SAML() *samlsp.Middleware
	// Refresh()
	// Register()
}

var _ Interface = &Authentication{}

type Authentication struct {
	Log      *zerolog.Logger
	Secret   string
	Duration time.Duration

	BaseURL *url.URL

	DB       r.QueryExecutor
	Client   isardvdi.Interface
	Notifier notifier.Invoker

	providers map[string]provider.Provider
	saml      *samlsp.Middleware
}

// TODO: Setup the notifier client
func Init(cfg cfg.Cfg, log *zerolog.Logger, db r.QueryExecutor) *Authentication {
	a := &Authentication{
		Log:      log,
		Secret:   cfg.Authentication.Secret,
		Duration: cfg.Authentication.TokenDuration,
		DB:       db,
		BaseURL: &url.URL{
			Scheme: "https",
			Host:   cfg.Authentication.Host,
		},
	}

	cli, err := isardvdi.NewClient(&isardvdi.Cfg{
		Host: "http://isard-api:5000",
	})
	if err != nil {
		log.Fatal().Err(err).Msg("create API client")
	}

	cli.BeforeRequestHook = func(c *isardvdi.Client) error {
		ss, err := jwt.SignAPIJWT(a.Secret)
		if err != nil {
			return err
		}

		c.SetToken(ss)

		return nil
	}

	a.Client = cli

	nCli, err := notifier.NewClient(cfg.Notifier.Address, notifier.WithClient(http.NewIsardVDIClient(a.Secret)))
	nCli.PostFrontend(context.Background(), notifier.OptNotifyFrontendRequest0bf6af6{})
	if err != nil {
		log.Fatal().Err(err).Msg("create notifier client")
	}

	a.Notifier = nCli

	providers := map[string]provider.Provider{
		types.Unknown:  &provider.Unknown{},
		types.Form:     provider.InitForm(cfg.Authentication, db),
		types.External: &provider.External{},
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
		if k == types.Unknown || k == types.External {
			continue
		}

		if k == types.Form {
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
		return a.providers[types.Unknown]
	}

	return prv
}

func (a *Authentication) Login(ctx context.Context, prv, categoryID string, args map[string]string) (string, string, error) {
	// Check if the user sends a token
	if args[provider.TokenArgsKey] != "" {
		typ, err := token.GetTokenType(args[provider.TokenArgsKey])
		if err != nil {
			return "", "", fmt.Errorf("get the JWT token type: %w", err)
		}

		switch typ {
		case token.TypeRegister:
			return a.finishRegister(ctx, args[provider.TokenArgsKey], args[provider.RedirectArgsKey])

		case token.TypeDisclaimerAcknowledgementRequired:
			return a.finishDisclaimerAcknowledgement(ctx, args[provider.TokenArgsKey], args[provider.RedirectArgsKey])

		case token.TypePasswordResetRequired:
			return a.finishPasswordReset(ctx, args[provider.TokenArgsKey], args[provider.RedirectArgsKey])
		}
	}

	// Get the provider and log in
	p := a.Provider(prv)
	g, u, redirect, err := p.Login(ctx, categoryID, args)
	if err != nil {
		a.Log.Info().Str("prv", p.String()).Err(err).Msg("login failed")

		return "", "", fmt.Errorf("login: %w", err)
	}

	// If the provider forces us to redirect, do it
	if redirect != "" {
		return "", redirect, nil
	}

	// Remove weird characters from the user and group names
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

func (a *Authentication) Callback(ctx context.Context, ss string, args map[string]string) (string, string, error) {
	claims, err := token.ParseCallbackToken(a.Secret, ss)
	if err != nil {
		return "", "", fmt.Errorf("parse callback state: %w", err)
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

	// Remove weird characters from the user name
	normalizeIdentity(nil, u)

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

	// Check if the user needs to acknowledge the disclaimer
	dscl, err := a.Client.AdminUserRequiredDisclaimerAcknowledgement(ctx, u.ID)
	if err != nil {
		return "", "", fmt.Errorf("check if the user needs to accept the disclaimer: %w", err)
	}
	if dscl {
		ss, err := token.SignDisclaimerAcknowledgementRequiredToken(a.Secret, u.ID)
		if err != nil {
			return "", "", err
		}

		return ss, redirect, nil
	}

	// Check if the user has the email verified
	vfEmail, err := a.Client.AdminUserRequiredEmailVerification(ctx, u.ID)
	if err != nil {
		return "", "", fmt.Errorf("check if the user needs to verify the email: %w", err)
	}
	if vfEmail {
		ss, err := token.SignEmailVerificationRequiredToken(a.Secret, u)
		if err != nil {
			return "", "", err
		}

		return ss, redirect, nil
	}

	pwdRst, err := a.Client.AdminUserRequiredPasswordReset(ctx, u.ID)
	if err != nil {
		return "", "", fmt.Errorf("check if the user needs to reset the password: %w", err)
	}
	if pwdRst {
		ss, err := token.SignPasswordResetRequiredToken(a.Secret, u.ID)
		if err != nil {
			return "", "", err
		}

		return ss, redirect, nil
	}

	// Set the last accessed time of the user
	u.Accessed = float64(time.Now().Unix())

	// Load the rest of the data of the user from the DB without overriding the data provided by the
	// login provider
	u2 := &model.User{ID: u.ID}
	if err := u2.Load(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("load user from DB: %w", err)
	}

	u.LoadWithoutOverride(u2)
	normalizeIdentity(nil, u)

	// Update the user in the DB with the latest data
	if err := u.Update(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("update user in the DB: %w", err)
	}

	ss, err := token.SignLoginToken(a.Secret, a.Duration, u)
	if err != nil {
		return "", "", err
	}

	a.Log.Info().Str("usr", u.ID).Str("tkn", ss).Str("redirect", redirect).Msg("login succeeded")

	return ss, redirect, nil
}

func (a *Authentication) finishRegister(ctx context.Context, ss, redirect string) (string, string, error) {
	claims, err := token.ParseRegisterToken(a.Secret, ss)
	if err != nil {
		return "", "", err
	}

	u := &model.User{
		Provider: claims.Provider,
		Category: claims.CategoryID,
		UID:      claims.UserID,
	}
	if err := u.LoadWithoutID(ctx, a.DB); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			return "", "", errors.New("user not registered")
		}

		return "", "", fmt.Errorf("load user from db: %w", err)
	}

	ss, redirect, err = a.finishLogin(ctx, u, redirect)
	if err != nil {
		return "", "", err
	}

	a.Log.Info().Str("usr", u.ID).Str("tkn", ss).Msg("register succeeded")

	return ss, redirect, nil
}

func (a *Authentication) finishDisclaimerAcknowledgement(ctx context.Context, ss, redirect string) (string, string, error) {
	claims, err := token.ParseDisclaimerAcknowledgementRequiredToken(a.Secret, ss)
	if err != nil {
		return "", "", err
	}

	u := &model.User{ID: claims.UserID}
	if err := u.Load(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("load user from db: %w", err)
	}

	return a.finishLogin(ctx, u, redirect)
}

func (a *Authentication) finishPasswordReset(ctx context.Context, ss, redirect string) (string, string, error) {
	claims, err := token.ParsePasswordResetRequiredToken(a.Secret, ss)
	if err != nil {
		return "", "", err
	}

	u := &model.User{ID: claims.UserID}
	if err := u.Load(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("load user from db: %w", err)
	}

	return a.finishLogin(ctx, u, redirect)
}

func (a *Authentication) Check(ctx context.Context, ss string) error {
	_, err := token.ParseLoginToken(a.Secret, ss)
	if err != nil {
		return err
	}

	return nil
}

func (a *Authentication) SAML() *samlsp.Middleware {
	return a.saml
}
