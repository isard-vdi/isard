package authentication

import (
	"context"
	"fmt"
	"net/url"
	"sync"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/gen/oas/notifier"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"

	"github.com/crewjam/saml/samlsp"
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi/pkg/sdk"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Interface interface {
	Providers() []string
	Provider(provider string) provider.Provider

	Login(ctx context.Context, provider string, categoryID string, args provider.LoginArgs, remoteAddr string) (tkn, redirect string, err error)
	Callback(ctx context.Context, ss string, args provider.CallbackArgs, remoteAddr string) (tkn, redirect string, err error)
	Check(ctx context.Context, tkn string, remoteAddr string) error
	Renew(ctx context.Context, ss string, remoteAddr string) (tkn string, err error)
	Logout(ctx context.Context, tkn string) (redirect string, err error)
	// Register()

	AcknowledgeDisclaimer(ctx context.Context, tkn string) error
	RequestEmailVerification(ctx context.Context, tkn string, email string) error
	VerifyEmail(ctx context.Context, tkn string) error
	ForgotPassword(ctx context.Context, categoryID, email string) error
	ResetPassword(ctx context.Context, tkn string, pwd string, remoteAddr string) error
	MigrateUser(ctx context.Context, tkn string, UserID string) (migrationTkn string, err error)
	// External
	ExternalUser(ctx context.Context, tkn string, UserID string, role string, username string, name string, email string, photo string) (apiKey string, err error)
	GenerateAPIKey(ctx context.Context, tkn string, expirationMinutes int) (apiKey string, err error)
	GenerateUserToken(ctx context.Context, tkn string, userID string) (userTkn string, err error)

	SAML() *samlsp.Middleware

	Healthcheck() error
}

var _ Interface = &Authentication{}

type Authentication struct {
	Log    *zerolog.Logger
	Secret string

	BaseURL *url.URL

	DB       r.QueryExecutor
	API      sdk.Interface
	Notifier notifier.Invoker
	Sessions sessionsv1.SessionsServiceClient

	Cfg cfg.Authentication

	prvManager *ProviderManager
}

func Init(ctx context.Context, wg *sync.WaitGroup, cfg cfg.Cfg, log *zerolog.Logger, db r.QueryExecutor, apiCli sdk.Interface, notifierCli notifier.Invoker, sessionsCli sessionsv1.SessionsServiceClient) *Authentication {
	a := &Authentication{
		Log:    log,
		Secret: cfg.Authentication.Secret,

		BaseURL: &url.URL{
			Scheme: "https",
			Host:   cfg.Authentication.Host,
		},

		DB:         db,
		API:        apiCli,
		Notifier:   notifierCli,
		Sessions:   sessionsCli,
		Cfg:        cfg.Authentication,
		prvManager: InitProviderManager(ctx, wg, cfg.Authentication, log, db),
	}

	return a
}

func (a *Authentication) Providers() []string {
	return a.prvManager.Providers()
}

func (a *Authentication) Provider(p string) provider.Provider {
	return a.prvManager.Provider(p)
}

func (a *Authentication) check(ctx context.Context, ss, remoteAddr string) (*token.LoginClaims, error) {
	claims, err := token.ParseLoginToken(a.Secret, ss)
	if err != nil {
		return nil, err
	}

	if _, err := a.Sessions.Get(ctx, &sessionsv1.GetRequest{
		Id:         claims.SessionID,
		RemoteAddr: remoteAddr,
	}); err != nil {
		return nil, fmt.Errorf("get the session: %w", err)
	}

	return claims, nil
}

func (a *Authentication) Check(ctx context.Context, ss, remoteAddr string) error {
	_, err := a.check(ctx, ss, remoteAddr)
	return err
}

func (a *Authentication) SAML() *samlsp.Middleware {
	return a.prvManager.SAML()
}

func (a *Authentication) Healthcheck() error {
	return a.prvManager.Healthcheck()
}
