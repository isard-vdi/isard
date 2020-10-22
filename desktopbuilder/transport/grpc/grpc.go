package grpc

import (
	"context"
	"sync"

	"gitlab.com/isard/isardvdi/desktopbuilder/desktopbuilder"
	"gitlab.com/isard/isardvdi/desktopbuilder/pkg/proto"

	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi/common/pkg/grpc"
	gRPC "google.golang.org/grpc"
)

type DesktopBuilderServer struct {
	DesktopBuilder desktopbuilder.Interface
	Addr           string

	Log *zerolog.Logger
	WG  *sync.WaitGroup

	proto.UnimplementedDesktopBuilderServer
}

func (d *DesktopBuilderServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, d.Log, d.WG, func(s *gRPC.Server) {
		proto.RegisterDesktopBuilderServer(s, d)
	}, d.Addr)
}
