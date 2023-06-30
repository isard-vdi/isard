package authentication

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/crewjam/saml/samlsp"
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-sdk-go"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

const adminUsr = "local-default-admin-admin"

type Interface interface {
	Providers() []string
	Provider(provider string) provider.Provider
	Login(ctx context.Context, provider string, categoryID string, args map[string]string) (tkn, redirect string, err error)
	Callback(ctx context.Context, args map[string]string) (tkn, redirect string, err error)
	Check(ctx context.Context, tkn string) error
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

type apiRegisterUserRsp struct {
	ID string `json:"id"`
}

// TODO: Make this use the isardvdi-go-sdk and the pkg/jwt package
func (a *Authentication) registerUser(u *model.User) error {
	tkn, err := a.signRegisterToken(u)
	if err != nil {
		return err
	}

	login, err := a.signLoginToken(u)
	if err != nil {
		return err
	}

	req, err := http.NewRequest(http.MethodPost, "http://isard-api:5000/api/v3/user/auto-register", nil)
	if err != nil {
		return fmt.Errorf("create http request: %w", err)
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", tkn))
	req.Header.Set("Login-Claims", fmt.Sprintf("Bearer %s", login))

	rsp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("do http request: %w", err)
	}

	if rsp.StatusCode != 200 {
		return fmt.Errorf("http code not 200: %d", rsp.StatusCode)
	}

	r := &apiRegisterUserRsp{}
	defer rsp.Body.Close()
	if err := json.NewDecoder(rsp.Body).Decode(r); err != nil {
		return fmt.Errorf("parse auto register JSON response: %w", err)
	}
	u.ID = r.ID
	u.Active = true

	return nil
}

// TODO: Make this use the pkg/jwt package
func (a *Authentication) registerGroup(g *model.Group) error {
	cli, err := isardvdi.NewClient(&isardvdi.Cfg{
		Host: "http://isard-api:5000",
	})
	if err != nil {
		return fmt.Errorf("create API client: %w", err)
	}

	u := &model.User{ID: adminUsr}
	if err := u.Load(context.Background(), a.DB); err != nil {
		return fmt.Errorf("load the admin user from the DB: %w", err)
	}

	tkn, err := a.signLoginToken(u)
	if err != nil {
		return fmt.Errorf("sign the admin token to register the group: %w", err)
	}
	cli.Token = tkn

	grp, err := cli.AdminGroupCreate(
		context.Background(),
		g.Category,
		// TODO: When UUIDs arrive, this g.Name has to be removed and the dependency has to be updated to v0.14.1
		g.Name,
		g.Name,
		g.Description,
		g.ExternalAppID,
		g.ExternalGID,
	)
	if err != nil {
		return fmt.Errorf("register the group: %w", err)
	}

	g.ID = isardvdi.GetString(grp.ID)
	g.UID = isardvdi.GetString(grp.UID)

	return nil
}

func (a *Authentication) Login(ctx context.Context, prv, categoryID string, args map[string]string) (string, string, error) {
	// Check if the user sends a token
	if args[provider.TokenArgsKey] != "" {
		tkn, tknType, err := a.verifyToken(args[provider.TokenArgsKey])
		if err == nil {
			switch tknType {
			case tokenTypeRegister:
				register := tkn.Claims.(*RegisterClaims)

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

				ss, err := a.signLoginToken(u)
				if err != nil {
					return "", "", err
				}

				a.Log.Info().Str("usr", u.ID).Str("tkn", ss).Msg("register succeeded")

				return ss, args[provider.RedirectArgsKey], nil

			case tokenTypeExternal:
				claims := tkn.Claims.(*ExternalClaims)

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
			return "", "", fmt.Errorf("verify the JWT token: %w", err)
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

	uExists, err := u.Exists(ctx, a.DB)
	if err != nil {
		return "", "", fmt.Errorf("check if user exists: %w", err)
	}

	if !uExists {
		// Manual registration
		if !p.AutoRegister() {
			// If the user has logged in correctly, but doesn't exist in the DB, they have to register first!
			ss, err := a.signRegisterToken(u)

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

	// Check if the user is disabled
	if !u.Active {
		return "", "", provider.ErrUserDisabled
	}

	u.Accessed = float64(time.Now().Unix())

	u2 := &model.User{ID: u.ID}
	if err := u2.Load(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("load user from DB: %w", err)
	}

	u.LoadWithoutOverride(u2)
	if err := u.Update(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("update user in the DB: %w", err)
	}

	ss, err := a.signLoginToken(u)
	if err != nil {
		return "", "", err
	}

	if redirect == "" {
		redirect = args[provider.RedirectArgsKey]
	}

	a.Log.Info().Str("usr", u.ID).Str("tkn", ss).Str("redirect", redirect).Msg("login succeeded")

	return ss, redirect, nil
}

func (a *Authentication) Callback(ctx context.Context, args map[string]string) (string, string, error) {
	ss := args["state"]
	if ss == "" {
		return "", "", errors.New("callback state not provided")
	}

	tkn, err := a.parseAuthenticationToken(ss, &provider.CallbackClaims{})
	if err != nil {
		return "", "", fmt.Errorf("parse callback state: %w", err)
	}

	claims, ok := tkn.Claims.(*provider.CallbackClaims)
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

	if exists {
		// Check if the user is disabled
		if !u.Active {
			return "", "", provider.ErrUserDisabled
		}

		u.Accessed = float64(time.Now().Unix())

		u2 := &model.User{ID: u.ID}
		if err := u2.Load(ctx, a.DB); err != nil {
			return "", "", fmt.Errorf("load user from DB: %w", err)
		}

		u.LoadWithoutOverride(u2)
		if err := u.Update(ctx, a.DB); err != nil {
			return "", "", fmt.Errorf("update user in the DB: %w", err)
		}

		ss, err = a.signLoginToken(u)
		if err != nil {
			return "", "", err
		}

		logRedirect := redirect
		if logRedirect == "" {
			logRedirect = claims.Redirect
		}

		a.Log.Info().Str("usr", u.ID).Str("tkn", ss).Str("redirect", logRedirect).Msg("login succeeded")

	} else {
		ss, err = a.signRegisterToken(u)
		if err != nil {
			return "", "", err
		}

		a.Log.Info().Err(err).Str("usr", u.UID).Str("tkn", ss).Msg("register token signed")
	}

	if redirect == "" {
		redirect = claims.Redirect
	}

	return ss, redirect, nil
}

func (a *Authentication) Check(ctx context.Context, ss string) error {
	tkn, err := a.parseAuthenticationToken(ss, &LoginClaims{})
	if err != nil {
		return err
	}

	_, ok := tkn.Claims.(*LoginClaims)
	if !ok {
		return errors.New("unknown JWT claims format")
	}

	return nil
}

func (a *Authentication) SAML() *samlsp.Middleware {
	return a.saml
}
