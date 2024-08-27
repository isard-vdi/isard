package provider

import (
	"context"
	"fmt"
	"net/http"
	"strings"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"

	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"
	gAPI "google.golang.org/api/oauth2/v2"
	"google.golang.org/api/option"
)

var _ Provider = &Google{}

type Google struct {
	provider *oauth2Provider
}

func InitGoogle(cfg cfg.Authentication) *Google {
	return &Google{
		&oauth2Provider{
			types.ProviderGoogle,
			cfg.Secret,
			&oauth2.Config{
				ClientID:     cfg.Google.ClientID,
				ClientSecret: cfg.Google.ClientSecret,
				Scopes: []string{
					"https://www.googleapis.com/auth/userinfo.email",
					"https://www.googleapis.com/auth/userinfo.profile",
				},
				Endpoint:    google.Endpoint,
				RedirectURL: fmt.Sprintf("https://%s/authentication/callback", cfg.Host),
			},
		},
	}
}

func (g *Google) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	redirect := ""
	if args.Redirect != nil {
		redirect = *args.Redirect
	}

	redirect, err := g.provider.login(categoryID, redirect)
	if err != nil {
		return nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}

	return nil, nil, redirect, "", nil
}

func (g *Google) Callback(ctx context.Context, claims *token.CallbackClaims, args CallbackArgs) (*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	oTkn, err := g.provider.callback(ctx, args)
	if err != nil {
		return nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}

	svc, err := gAPI.NewService(ctx, option.WithTokenSource(oauth2.StaticTokenSource(oTkn)))
	if err != nil {
		return nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("create Google API client: %w", err),
		}
	}

	gUsr, err := svc.Userinfo.Get().Do()
	if err != nil {
		return nil, nil, "", "", &ProviderError{
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

	return nil, u, "", "", nil
}

func (Google) AutoRegister(*model.User) bool {
	return false
}

func (g *Google) String() string {
	return types.ProviderGoogle
}

func (g *Google) Healthcheck() error {
	_, err := http.PostForm("https://oauth2.googleapis.com/token", nil)
	if err != nil {
		return fmt.Errorf("check google oauth2 endpoint: %w", err)
	}

	return nil
}
