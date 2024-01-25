package provider

import (
	"context"
	"fmt"
	"net/http"
	"strings"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"

	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"
	gAPI "google.golang.org/api/oauth2/v2"
	"google.golang.org/api/option"
)

type Google struct {
	provider *oauth2Provider
}

func InitGoogle(cfg cfg.Authentication) *Google {
	return &Google{
		&oauth2Provider{
			types.Google,
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

func (g *Google) Login(ctx context.Context, categoryID string, args map[string]string) (*model.Group, *model.User, string, error) {
	redirect := args["redirect"]
	redirect, err := g.provider.login(categoryID, redirect)
	if err != nil {
		return nil, nil, "", err
	}

	return nil, nil, redirect, nil
}

func (g *Google) Callback(ctx context.Context, claims *token.CallbackClaims, args map[string]string) (*model.Group, *model.User, string, error) {
	oTkn, err := g.provider.callback(ctx, args)
	if err != nil {
		return nil, nil, "", err
	}

	svc, err := gAPI.NewService(ctx, option.WithTokenSource(oauth2.StaticTokenSource(oTkn)))
	if err != nil {
		return nil, nil, "", fmt.Errorf("create Google API client: %w", err)
	}

	gUsr, err := svc.Userinfo.Get().Do()
	if err != nil {
		return nil, nil, "", fmt.Errorf("get user information from Google: %w", err)
	}

	u := &model.User{
		UID:      gUsr.Id,
		Username: strings.Split(gUsr.Email, "@")[0],
		Provider: claims.Provider,
		Category: claims.CategoryID,
		Name:     gUsr.Name,
		Email:    gUsr.Email,
		Photo:    gUsr.Picture,
	}

	return nil, u, "", nil
}

func (Google) AutoRegister() bool {
	return false
}

func (g *Google) String() string {
	return types.Google
}

func (g *Google) Healthcheck() error {
	_, err := http.PostForm("https://oauth2.googleapis.com/token", nil)
	if err != nil {
		return fmt.Errorf("check google oauth2 endpoint: %w", err)
	}

	return nil
}
