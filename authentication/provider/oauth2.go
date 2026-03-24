package provider

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/token"

	"golang.org/x/oauth2"
)

type oauth2Provider struct {
	secret   string
	provider string

	cfg *cfgManager[oauth2.Config]
}

type oauth2ProviderConfig struct {
	clientID     string
	clientSecret string
}

func (o *oauth2Provider) loadConfig(cfg oauth2ProviderConfig) {
	prvCfg := o.cfg.Cfg()
	prvCfg.ClientID = cfg.clientID
	prvCfg.ClientSecret = cfg.clientSecret

	o.cfg.LoadCfg(prvCfg)
}

func (o *oauth2Provider) login(host, categoryID, redirect string) (string, error) {
	ss, err := token.SignCallbackToken(o.secret, o.provider, categoryID, redirect)
	if err != nil {
		return "", fmt.Errorf("sign the callback token: %w", err)
	}

	cfg := o.cfgWithHost(host)
	return cfg.AuthCodeURL(ss), nil
}

func (o *oauth2Provider) cfgWithHost(host string) oauth2.Config {
	cfg := o.cfg.Cfg()
	cfg.RedirectURL = fmt.Sprintf("https://%s/authentication/callback", host)
	return cfg
}

func (o *oauth2Provider) callback(ctx context.Context, args CallbackArgs) (*oauth2.Token, error) {
	code := ""
	if args.Oauth2Code != nil {
		code = *args.Oauth2Code
	}

	cfg := o.cfgWithHost(args.Host)
	tkn, err := cfg.Exchange(ctx, code)
	if err != nil {
		return nil, fmt.Errorf("exchange oauth2 token: %w", err)
	}

	return tkn, nil
}
