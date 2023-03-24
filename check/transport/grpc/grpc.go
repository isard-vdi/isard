package grpc

import (
	"context"
	"errors"
	"sync"

	"gitlab.com/isard/isardvdi-cli/pkg/client"
	"gitlab.com/isard/isardvdi/check/check"
	checkv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/check/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"

	"github.com/rs/zerolog"
	gRPC "google.golang.org/grpc"
)

func NewCheckServer(log *zerolog.Logger, wg *sync.WaitGroup, addr string, check check.Interface) *CheckServer {
	return &CheckServer{
		check: check,
		addr:  addr,

		log: log,
		wg:  wg,
	}
}

type CheckServer struct {
	check check.Interface
	addr  string

	log *zerolog.Logger
	wg  *sync.WaitGroup

	checkv1.UnimplementedCheckServiceServer
}

func (c *CheckServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, c.log, c.wg, func(s *gRPC.Server) {
		checkv1.RegisterCheckServiceServer(s, c)
	}, c.addr)
}

func (c *CheckServer) getAuth(req *checkv1.Auth) (check.AuthMethod, check.Auth, error) {
	switch a := req.GetMethod().(type) {
	case *checkv1.Auth_Form:
		return check.AuthMethodForm, check.Auth{
			Form: &check.AuthForm{
				Category: a.Form.Category,
				Username: a.Form.Username,
				Password: a.Form.Password,
			},
		}, nil

	case *checkv1.Auth_Token:
		return check.AuthMethodToken, check.Auth{
			Token: &check.AuthToken{
				Token: a.Token.Token,
			},
		}, nil
	}

	return check.AuthMethodUnknown, check.Auth{}, errors.New("unsupported auth method")
}

func (c *CheckServer) CheckIsardVDI(ctx context.Context, req *checkv1.CheckIsardVDIRequest) (*checkv1.CheckIsardVDIResponse, error) {
	method, auth, err := c.getAuth(req.GetAuth())
	if err != nil {
		return nil, err
	}

	result, err := c.check.CheckIsardVDI(ctx, method, auth, req.Host, req.TemplateId, req.FailSelfSigned, req.FailMaintenanceMode)
	if err != nil {
		c.log.Error().Err(err).Msg("check failed")
		return nil, err
	}

	return &checkv1.CheckIsardVDIResponse{
		IsardvdiVersion:    result.IsardVDIVersion,
		MaintenanceMode:    result.MaintenanceMode,
		IsardvdiSdkVersion: client.Version,
		DependenciesVersions: &checkv1.DependenciesVersions{
			Remmina:      result.DependenciesVersions.Remmina,
			RemoteViewer: result.DependenciesVersions.RemoteViewer,
			Wireguard:    result.DependenciesVersions.WireGuard,
		},
		HypervisorNum: int32(result.HypervisorNum),
	}, nil
}

func (c *CheckServer) CheckHypervisor(ctx context.Context, req *checkv1.CheckHypervisorRequest) (*checkv1.CheckHypervisorResponse, error) {
	method, auth, err := c.getAuth(req.GetAuth())
	if err != nil {
		return nil, err
	}

	result, err := c.check.CheckHypervisor(ctx, method, auth, req.Host, req.HypervisorId, req.TemplateId, req.FailSelfSigned, req.FailMaintenanceMode)
	if err != nil {
		c.log.Error().Err(err).Msg("check failed")
		return nil, err
	}

	return &checkv1.CheckHypervisorResponse{
		IsardvdiVersion:    result.IsardVDIVersion,
		MaintenanceMode:    result.MaintenanceMode,
		IsardvdiSdkVersion: client.Version,
		DependenciesVersions: &checkv1.DependenciesVersions{
			Remmina:      result.DependenciesVersions.Remmina,
			RemoteViewer: result.DependenciesVersions.RemoteViewer,
			Wireguard:    result.DependenciesVersions.WireGuard,
		},
	}, nil
}
