package provider

import (
	"context"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt"
	"golang.org/x/oauth2"
)

type oauth2Provider struct {
	provider string
	secret   string
	cfg      *oauth2.Config
}

func (o *oauth2Provider) login(categoryID, redirect string) (string, error) {
	tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &CallbackClaims{
		&jwt.StandardClaims{
			Issuer:    "isard-authentication",
			ExpiresAt: time.Now().Add(10 * time.Minute).Unix(),
		},
		o.provider,
		categoryID,
		redirect,
	})

	ss, err := tkn.SignedString([]byte(o.secret))
	if err != nil {
		return "", fmt.Errorf("sign the token: %w", err)
	}

	return o.cfg.AuthCodeURL(ss), nil
}

func (o *oauth2Provider) callback(ctx context.Context, args map[string]string) (string, error) {
	tkn, err := o.cfg.Exchange(ctx, args["code"])
	if err != nil {
		return "", fmt.Errorf("exchange oauth2 token: %w", err)
	}

	return tkn.AccessToken, nil
}
