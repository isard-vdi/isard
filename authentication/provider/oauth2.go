package provider

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/token"

	"golang.org/x/oauth2"
)

type oauth2Provider struct {
	provider string
	secret   string
	cfg      *oauth2.Config
}

func (o *oauth2Provider) login(categoryID, redirect string) (string, error) {
	ss, err := token.SignCallbackToken(o.secret, o.provider, categoryID, redirect)
	if err != nil {
		return "", fmt.Errorf("sign the callback token: %w", err)
	}

	return o.cfg.AuthCodeURL(ss), nil
}

func (o *oauth2Provider) callback(ctx context.Context, args CallbackArgs) (*oauth2.Token, error) {
	code := ""
	if args.Oauth2Code != nil {
		code = *args.Oauth2Code
	}

	tkn, err := o.cfg.Exchange(ctx, code)
	if err != nil {
		return nil, fmt.Errorf("exchange oauth2 token: %w", err)
	}

	return tkn, nil
}
