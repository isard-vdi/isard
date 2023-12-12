package http

import (
	"fmt"
	"net/http"

	"gitlab.com/isard/isardvdi/pkg/jwt"
)

func NewIsardVDIClient(secret string) *http.Client {
	return &http.Client{
		Transport: &authenticatedTransport{
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
