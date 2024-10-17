package http

import (
	"fmt"
	"net/http"

	"gitlab.com/isard/isardvdi/pkg/gen/oas/notifier"
	"gitlab.com/isard/isardvdi/pkg/jwt"

	"gitlab.com/isard/isardvdi/pkg/sdk"
)

func NewIsardVDIClient(secret string) *http.Client {
	return &http.Client{
		Transport: &authenticatedTransport{
			secret:    secret,
			Transport: http.DefaultTransport,
		},
	}
}

type authenticatedTransport struct {
	Transport http.RoundTripper
	secret    string
}

func (a *authenticatedTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	ss, err := jwt.SignAPIJWT(a.secret)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", ss))

	return a.Transport.RoundTrip(req)
}

func NewAPIClient(addr, secret string) (sdk.Interface, error) {
	cli, err := sdk.NewClient(&sdk.Cfg{
		Host: addr,
	})
	if err != nil {
		return nil, err
	}

	cli.BeforeRequestHook = func(c *sdk.Client) error {
		ss, err := jwt.SignAPIJWT(secret)
		if err != nil {
			return err
		}

		c.SetToken(ss)

		return nil
	}

	return cli, nil
}

func NewNotifierClient(addr, secret string) (notifier.Invoker, error) {
	return notifier.NewClient(addr, notifier.WithClient(NewIsardVDIClient(secret)))
}
