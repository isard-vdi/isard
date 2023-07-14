package rdpgw

import (
	"context"
	"errors"
	"fmt"
	"net"
	"time"

	"github.com/bolkedebruin/rdpgw/protocol"
	"github.com/patrickmn/go-cache"
	"gitlab.com/isard/isardvdi-sdk-go"
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

		cli, err := isardvdi.NewClient(&isardvdi.Cfg{
			Host:  fmt.Sprintf("http://%s", apiAddr),
			Token: tkn.(string),
		})
		if err != nil {
			return false, fmt.Errorf("error creating the client: %w", err)
		}

		if err := cli.UserOwnsDesktop(ctx, &isardvdi.UserOwnsDesktopOpts{
			IP: ip,
		}); err != nil {
			if errors.Is(err, isardvdi.ErrForbidden) {
				return false, errors.New("unauthorized")
			}

			return false, fmt.Errorf("unknown error: %w", err)
		}

		return true, nil
	}
}
