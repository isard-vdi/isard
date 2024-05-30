package authentication

import (
	"context"
	"fmt"
	"net/url"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/pkg/gen/oas/notifier"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"

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
	Renew(ctx context.Context, ss string) (tkn string, err error)
	Logout(ctx context.Context, tkn string) (err error)
	// Register()

	AcknowledgeDisclaimer(ctx context.Context, tkn string) error
	RequestEmailVerification(ctx context.Context, tkn string, email string) error
	VerifyEmail(ctx context.Context, tkn string) error
	ForgotPassword(ctx context.Context, categoryID, email string) error
	ResetPassword(ctx context.Context, tkn string, pwd string) error

	SAML() *samlsp.Middleware

	Healthcheck() error
}

var _ Interface = &Authentication{}

type Authentication struct {
	Log    *zerolog.Logger
	Secret string

	BaseURL *url.URL

	DB       r.QueryExecutor
	API      isardvdi.Interface
	Notifier notifier.Invoker
	Sessions sessionsv1.SessionsServiceClient

	providers map[string]provider.Provider
	saml      *samlsp.Middleware
}

func Init(cfg cfg.Cfg, log *zerolog.Logger, db r.QueryExecutor, apiCli isardvdi.Interface, notifierCli notifier.Invoker, sessionsCli sessionsv1.SessionsServiceClient) *Authentication {
	a := &Authentication{
		Log:    log,
		Secret: cfg.Authentication.Secret,

		BaseURL: &url.URL{
			Scheme: "https",
			Host:   cfg.Authentication.Host,
		},

		DB:       db,
		API:      apiCli,
		Notifier: notifierCli,
		Sessions: sessionsCli,
	}

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

func (a *Authentication) check(ctx context.Context, ss string) (*token.LoginClaims, error) {
	claims, err := token.ParseLoginToken(a.Secret, ss)
	if err != nil {
		return nil, err
	}

	if _, err := a.Sessions.Get(ctx, &sessionsv1.GetRequest{
		Id: claims.SessionID,
	}); err != nil {
		return nil, fmt.Errorf("get the session: %w", err)
	}

	return claims, nil
}

func (a *Authentication) Check(ctx context.Context, ss string) error {
	_, err := a.check(ctx, ss)
	return err
}

func (a *Authentication) SAML() *samlsp.Middleware {
	return a.saml
}

func (a *Authentication) Healthcheck() error {
	for _, p := range a.providers {
		if err := p.Healthcheck(); err != nil {
			a.Log.Warn().Err(err).Str("provider", p.String()).Msg("service unhealthy")

			return err
		}
	}

	return nil
}
