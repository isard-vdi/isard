package rdpgw

import (
	"context"
	"errors"
	"fmt"
	"net"
	"time"

	"github.com/bolkedebruin/rdpgw/protocol"
	"github.com/patrickmn/go-cache"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
	"gitlab.com/isard/isardvdi/rdpgw/cfg"
)

var c = cache.New(5*time.Minute, 10*time.Minute)

func Init(cfg cfg.Cfg) *protocol.Gateway {
	return &protocol.Gateway{ServerConf: &protocol.ServerConf{
		IdleTimeout: int(cfg.IdleTimeout.Minutes()),
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
		tknAny, ok := c.Get(s.ConnId)
		if !ok {
			return false, errors.New("missing token")
		}
		tkn, ok := tknAny.(string)
		if !ok {
			return false, fmt.Errorf("unexpected token type %T", tknAny)
		}

		ip, _, err := net.SplitHostPort(host)
		if err != nil {
			return false, fmt.Errorf("split host ip and port: %w", err)
		}

		httpClient := ogenclient.NewHTTPClient()
		cli, err := apiv4.NewClient(
			fmt.Sprintf("http://%s", apiAddr),
			ogenclient.APIv4Static{Token: tkn},
			apiv4.WithClient(httpClient),
		)
		if err != nil {
			return false, fmt.Errorf("error creating the client: %w", err)
		}

		res, err := cli.UserOwnsDesktop(ctx, &apiv4.UserOwnsDesktopRequest{
			IP: apiv4.NewOptNilString(ip),
		})
		if err != nil {
			return false, fmt.Errorf("unknown error: %w", err)
		}
		if _, ok := res.(*apiv4.EmptyResponse); ok {
			return true, nil
		}

		apiErr := ogenclient.AsAPIError(res)
		if errors.Is(apiErr, ogenclient.ErrForbidden) {
			return false, errors.New("unauthorized")
		}
		return false, fmt.Errorf("unexpected API response: %w", apiErr)
	}
}
