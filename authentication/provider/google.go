package provider

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/db"

	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"
	gAPI "google.golang.org/api/oauth2/v2"
	"google.golang.org/api/option"

	"github.com/patrickmn/go-cache"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var _ Provider = &Google{}

type Google struct {
	provider *oauth2Provider
	rqe      r.QueryExecutor
}

type GoogleConfig struct {
	ClientID     string `rethinkdb:"client_id"`
	ClientSecret string `rethinkdb:"client_secret"`
}

func InitGoogle(cfg cfg.Authentication, rqe r.QueryExecutor) *Google {
	return &Google{
		&oauth2Provider{
			types.ProviderGoogle,
			cfg.Secret,
			&oauth2.Config{
				Scopes: []string{
					"https://www.googleapis.com/auth/userinfo.email",
					"https://www.googleapis.com/auth/userinfo.profile",
				},
				Endpoint:    google.Endpoint,
				RedirectURL: fmt.Sprintf("https://%s/authentication/callback", cfg.Host),
			},
		},
		rqe,
	}
}

func (g *Google) GoogleConfig() error {
	googleConfig := &GoogleConfig{}
	if val, found := c.Get("google_config"); found {
		googleConfig = val.(*GoogleConfig)
	} else {
		res, err := r.Table("config").Get(1).Field("auth").Field("google").Field("google_config").Run(g.rqe)
		if err != nil {
			return &db.Err{
				Err: err,
			}
		}
		if res.IsNil() {
			return db.ErrNotFound
		}
		defer res.Close()
		if err := res.One(googleConfig); err != nil {
			return &db.Err{
				Msg: "read db response",
				Err: err,
			}
		}
		c.Set("google_config", googleConfig, cache.DefaultExpiration)
	}
	g.provider.cfg.ClientID = googleConfig.ClientID
	g.provider.cfg.ClientSecret = googleConfig.ClientSecret
	return nil
}

func (g *Google) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	redirect := ""
	if args.Redirect != nil {
		redirect = *args.Redirect
	}

	if err := g.GoogleConfig(); err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}

	redirect, err := g.provider.login(categoryID, redirect)
	if err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}

	return nil, []*model.Group{}, nil, redirect, "", nil
}

func (g *Google) Callback(ctx context.Context, claims *token.CallbackClaims, args CallbackArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	if err := g.GoogleConfig(); err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}
	oTkn, err := g.provider.callback(ctx, args)
	if err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}

	svc, err := gAPI.NewService(ctx, option.WithTokenSource(oauth2.StaticTokenSource(oTkn)))
	if err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("create Google API client: %w", err),
		}
	}

	gUsr, err := svc.Userinfo.Get().Do()
	if err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("get user information from Google: %w", err),
		}
	}

	u := &types.ProviderUserData{
		Provider: claims.Provider,
		Category: claims.CategoryID,
		UID:      gUsr.Id,

		Username: &strings.Split(gUsr.Email, "@")[0],
		Name:     &gUsr.Name,
		Email:    &gUsr.Email,
		Photo:    &gUsr.Picture,
	}

	return nil, []*model.Group{}, u, "", "", nil
}

func (Google) AutoRegister(*model.User) bool {
	return false
}

func (g *Google) String() string {
	return types.ProviderGoogle
}

func (g *Google) Healthcheck() error {
	resp, err := http.PostForm("https://oauth2.googleapis.com/token", nil)
	if err != nil {
		return fmt.Errorf("check google oauth2 endpoint: %w", err)
	}
	defer resp.Body.Close()

	return nil
}

func (Google) Logout(context.Context, string) (string, error) {
	return "", nil
}

func (Google) SaveEmail() bool {
	return true
}

func (Google) GuessGroups(context.Context, *types.ProviderUserData, []string) (*model.Group, []*model.Group, *ProviderError) {
	return nil, nil, &ProviderError{
		User:   ErrInvalidIDP,
		Detail: errors.New("the google provider doesn't support the guess groups operation"),
	}
}

func (Google) GuessRole(context.Context, *types.ProviderUserData, []string) (*model.Role, *ProviderError) {
	return nil, &ProviderError{
		User:   ErrInvalidIDP,
		Detail: errors.New("the google provider doesn't support the guess role operation"),
	}
}
