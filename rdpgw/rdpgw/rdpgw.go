package rdpgw

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"time"

	"github.com/bolkedebruin/rdpgw/protocol"
	"github.com/patrickmn/go-cache"
	"gitlab.com/isard/isardvdi/rdpgw/cfg"
)

var c = cache.New(5*time.Minute, 10*time.Minute)

func Init(cfg cfg.Cfg) *protocol.Gateway {
	return &protocol.Gateway{ServerConf: &protocol.ServerConf{
		IdleTimeout: cfg.IdleTimeout,
		TokenAuth:   true,
		RedirectFlags: protocol.RedirectFlags{
			Clipboard: true,
			Drive:     true,
			Printer:   true,
			Port:      true,
			Pnp:       true,
		},
		VerifyTunnelCreate: verifyToken,
		VerifyServerFunc:   verifyServer(cfg.APIAddr),
	}}
}

func verifyToken(ctx context.Context, tkn string) (bool, error) {
	s := ctx.Value("SessionInfo").(*protocol.SessionInfo)
	c.Set(s.ConnId, tkn, cache.DefaultExpiration)

	return true, nil
}

func verifyServer(apiAddr string) func(context.Context, string) (bool, error) {
	return func(ctx context.Context, host string) (bool, error) {
		s := ctx.Value("SessionInfo").(*protocol.SessionInfo)
		tkn, ok := c.Get(s.ConnId)
		if !ok {
			return false, errors.New("missing token")
		}

		ip, _, err := net.SplitHostPort(host)
		if err != nil {
			return false, fmt.Errorf("split host ip and port: %w", err)
		}

		u := &url.URL{
			Scheme: "http",
			Host:   apiAddr,
			Path:   "/api/v3/user/owns_desktop",
		}

		body := url.Values{}
		body.Set("ip", ip)

		req, err := http.NewRequest(http.MethodGet, u.String(), bytes.NewBufferString(body.Encode()))
		if err != nil {
			return false, err
		}

		req.Header.Add("Content-Type", "application/x-www-form-urlencoded")
		req.Header.Add("Content-Length", strconv.Itoa(len(body.Encode())))
		req.Header.Add("Authorization", fmt.Sprintf("Bearer %s", tkn))

		rsp, err := http.DefaultClient.Do(req)
		if err != nil {
			return false, fmt.Errorf("do http request: %w", err)
		}

		switch rsp.StatusCode {
		case http.StatusOK:
			return true, nil

		case http.StatusUnauthorized:
			return false, errors.New("unauthorized")

		default:
			b, err := io.ReadAll(rsp.Body)
			if err != nil {
				return false, fmt.Errorf("read all the response body: %w", err)
			}
			defer rsp.Body.Close()

			return false, fmt.Errorf("unknown error: %s", b)
		}
	}
}
