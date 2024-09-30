package sdk

import (
	"context"
	"errors"
	"fmt"
	"net/http"
)

type UserVPNRsp struct {
	Kind    *string `json:"kind,omitempty"`
	Content *string `json:"content,omitempty"`
}

func (c *Client) UserVPN(ctx context.Context) (string, error) {
	req, err := c.newRequest(http.MethodGet, "user/vpn/config", nil)
	if err != nil {
		return "", err
	}

	rsp := &UserVPNRsp{}
	if _, err := c.do(ctx, req, rsp); err != nil {
		return "", fmt.Errorf("get VPN configuration: %w", err)
	}

	if rsp.Content == nil {
		return "", errors.New("empty response content")
	}

	return *rsp.Content, nil
}

type UserOwnsDesktopOpts struct {
	IP             string
	ProxyVideo     string
	ProxyHyperHost string
	Port           int
}

func (c *Client) UserOwnsDesktop(ctx context.Context, opts *UserOwnsDesktopOpts) error {
	body := map[string]interface{}{}

	if opts != nil && opts.IP != "" {
		body["ip"] = opts.IP
		req, err := c.newJSONRequest(http.MethodGet, "user/owns_desktop", body)
		if err != nil {
			return err
		}

		if _, err := c.do(ctx, req, nil); err != nil {
			return fmt.Errorf("check if user owns desktop: %w", err)
		}

		return nil

	} else if opts != nil && opts.ProxyVideo != "" && opts.ProxyHyperHost != "" && opts.Port != 0 {
		body["proxy_video"] = opts.ProxyVideo
		body["proxy_hyper_host"] = opts.ProxyHyperHost
		body["port"] = opts.Port

		req, err := c.newJSONRequest(http.MethodGet, "user/owns_desktop", body)
		if err != nil {
			return err
		}

		if _, err := c.do(ctx, req, nil); err != nil {
			return fmt.Errorf("check if user owns desktop: %w", err)
		}

		return nil
	}

	return fmt.Errorf("invalid options: %+v", opts)
}
