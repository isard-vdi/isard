package isardvdi

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

func (c *Client) SetToken(tkn string) {
	c.Token = tkn
}

func (c *Client) AuthForm(ctx context.Context, category, usr, pwd string) (string, error) {
	u, err := addOptions("/authentication/login", map[string]string{
		"provider":    "form",
		"category_id": category,
		"username":    usr,
	})
	if err != nil {
		return "", err
	}

	body := url.Values{}
	body.Add("provider", "form")
	body.Add("category_id", category)
	body.Add("username", usr)
	body.Add("password", pwd)

	req, err := c.newRequest(http.MethodPost, u, body)
	if err != nil {
		return "", err
	}

	rsp, err := c.do(ctx, req, nil)
	if err != nil {
		return "", fmt.Errorf("form login: %w", err)
	}
	defer rsp.Body.Close()

	b, err := io.ReadAll(rsp.Body)
	if err != nil {
		return "", err
	}

	if rsp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("http code %d: %s", rsp.StatusCode, b)
	}

	tkn := strings.TrimSpace(string(b))
	c.SetToken(tkn)

	return tkn, nil
}
