package rdpgw

import (
	"context"
	"errors"
	"fmt"
	"net"
	"time"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
	"gitlab.com/isard/isardvdi/rdpgw/cfg"

	"github.com/bolkedebruin/rdpgw/protocol"
	"github.com/patrickmn/go-cache"
)

var c = cache.New(5*time.Minute, 10*time.Minute)

func Init(cfg cfg.Cfg) (*protocol.Gateway, error) {
	opts := []ogenclient.Option{ogenclient.WithUserAgent("isardvdi-rdpgw")}

	cli, err := apiv4.NewClient(
		"http://"+cfg.APIAddr,
		ogenclient.APIv4Context{},
		apiv4.WithClient(ogenclient.NewHTTPClient(opts...)),
	)
	if err != nil {
		return nil, fmt.Errorf("create the API client: %w", err)
	}

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
		VerifyServerFunc:   verifyServer(cli),
	}}, nil
}

func verifyToken(ctx context.Context, tkn string) (bool, error) {
	s := ctx.Value("SessionInfo").(*protocol.SessionInfo)
	c.Set(s.ConnId, tkn, cache.DefaultExpiration)

	return true, nil
}

func verifyServer(cli apiv4.Invoker) func(context.Context, string) (bool, error) {
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

		res, err := cli.UserOwnsDesktop(ogenclient.ContextWithAPIv4Token(ctx, tkn), &apiv4.UserOwnsDesktopRequest{
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
