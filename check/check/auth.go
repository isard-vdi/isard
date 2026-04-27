package check

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

type AuthMethod int

const (
	AuthMethodUnknown AuthMethod = iota
	AuthMethodForm
	AuthMethodToken
)

type Auth struct {
	Form  *AuthForm
	Token *AuthToken
}

type AuthForm struct {
	Category string
	Username string
	Password string
}

type AuthToken struct {
	Token string
}

// auth returns a bearer token for the given authentication method.
func (c *Check) auth(ctx context.Context, host string, ignoreCerts bool, method AuthMethod, auth Auth) (string, error) {
	switch method {
	case AuthMethodForm:
		return authForm(ctx, host, ignoreCerts, auth.Form)

	case AuthMethodToken:
		return auth.Token.Token, nil

	default:
		return "", errors.New("unknown authentication method")
	}
}

// authForm performs a form login against the authentication endpoint and returns
// the bearer token.
func authForm(ctx context.Context, host string, ignoreCerts bool, form *AuthForm) (string, error) {
	u, err := url.Parse(host)
	if err != nil {
		return "", fmt.Errorf("parse host: %w", err)
	}

	u.Path = "/authentication/login"
	q := u.Query()
	q.Set("provider", "form")
	q.Set("category_id", form.Category)
	q.Set("username", form.Username)
	u.RawQuery = q.Encode()

	body := url.Values{}
	body.Set("username", form.Username)
	body.Set("password", form.Password)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u.String(), strings.NewReader(body.Encode()))
	if err != nil {
		return "", fmt.Errorf("build login request: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	httpCli := http.DefaultClient
	if ignoreCerts {
		httpCli = &http.Client{
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{InsecureSkipVerify: true}, //nolint:gosec // Caller opted in.
			},
		}
	}

	rsp, err := httpCli.Do(req)
	if err != nil {
		return "", fmt.Errorf("form login: %w", err)
	}
	defer rsp.Body.Close()

	b, err := io.ReadAll(rsp.Body)
	if err != nil {
		return "", fmt.Errorf("read login response: %w", err)
	}

	if rsp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("http code %d: %s", rsp.StatusCode, b)
	}

	return strings.TrimSpace(string(b)), nil
}
