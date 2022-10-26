package provider

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"

	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"
)

const GoogleString = "google"

type Google struct {
	provider *oauth2Provider
}

func InitGoogle(cfg cfg.Authentication) *Google {
	return &Google{
		&oauth2Provider{
			GoogleString,
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

type googleAPIUsr struct {
	UID   string `json:"id,omitempty"`
	Name  string `json:"name,omitempty"`
	Email string `json:"email,omitempty"`
	Photo string `json:"picture,omitempty"`
}

func (g *Google) Callback(ctx context.Context, claims *CallbackClaims, args map[string]string) (*model.Group, *model.User, string, error) {
	oTkn, err := g.provider.callback(ctx, args)
	if err != nil {
		return nil, nil, "", err
	}

	q := url.Values{"access_token": {oTkn}}
	url := url.URL{
		Scheme:   "https",
		Host:     "www.googleapis.com",
		Path:     "oauth2/v2/userinfo",
		RawQuery: q.Encode(),
	}

	rsp, err := http.Get(url.String())
	if err != nil {
		return nil, nil, "", fmt.Errorf("call Google API: %w", err)
	}
	defer rsp.Body.Close()

	if rsp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(rsp.Body)

		return nil, nil, "", fmt.Errorf("call Google API: HTTP Code %d: %s", rsp.StatusCode, b)
	}

	gUsr := &googleAPIUsr{}
	if err := json.NewDecoder(rsp.Body).Decode(&gUsr); err != nil {
		return nil, nil, "", fmt.Errorf("unmarshal Google API json response: %w", err)
	}

	u := &model.User{
		UID:      gUsr.UID,
		Username: strings.Split(gUsr.Email, "@")[0],
		Provider: claims.Provider,
		Category: claims.CategoryID,
		Name:     gUsr.Name,
		Email:    gUsr.Email,
		Photo:    gUsr.Photo,
	}

	return nil, u, "", nil
}

func (Google) AutoRegister() bool {
	return false
}

func (g *Google) String() string {
	return GoogleString
}
