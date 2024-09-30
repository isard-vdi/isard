package sdk

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
)

type Template struct {
	ID   *string
	Name *string
}

func (c *Client) TemplateList(ctx context.Context) ([]*Template, error) {
	req, err := c.newRequest(http.MethodGet, "user/templates", nil)
	if err != nil {
		return nil, err
	}

	templates := []*Template{}
	if _, err := c.do(ctx, req, &templates); err != nil {
		return nil, fmt.Errorf("list templates: %w", err)
	}

	return templates, nil
}

func (c *Client) TemplateCreateFromDesktop(ctx context.Context, name string, desktopID string) (*Template, error) {
	body := url.Values{}
	body.Add("template_name", name)
	body.Add("desktop_id", desktopID)

	req, err := c.newRequest(http.MethodPost, "template", body)
	if err != nil {
		return nil, err
	}

	t := &Template{}
	if rsp, err := c.do(ctx, req, t); err != nil {
		fmt.Println(err)
		b, err2 := io.ReadAll(rsp.Body)
		fmt.Println(err2)
		fmt.Println(string(b))
		return nil, fmt.Errorf("create template: %w", err)
	}

	return t, nil
}
