package grpc

import (
	"context"
	"sync"

	"gitlab.com/isard/isardvdi/controller/controller"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	proto "gitlab.com/isard/isardvdi/pkg/proto/controller"

	"github.com/rs/zerolog"
	gRPC "google.golang.org/grpc"
)

type ControllerServer struct {
	Controller controller.Interface
	Addr       string

	Log *zerolog.Logger
	WG  *sync.WaitGroup

	proto.UnimplementedControllerServer
}

func (c *ControllerServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, c.Log, c.WG, func(s *gRPC.Server) {
		proto.RegisterControllerServer(s, c)
	}, c.Addr)
}
