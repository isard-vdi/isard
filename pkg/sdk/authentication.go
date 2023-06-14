package isardvdi

import (
	"context"
	"fmt"
	"io"
	"net/http"
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
		"password":    pwd,
	})
	if err != nil {
		return "", err
	}

	req, err := c.newRequest(http.MethodPost, u, nil)
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
