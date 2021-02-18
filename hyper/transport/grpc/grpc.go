package grpc

import (
	"context"
	"sync"

	"gitlab.com/isard/isardvdi/hyper/hyper"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	proto "gitlab.com/isard/isardvdi/pkg/proto/hyper"

	"github.com/rs/zerolog"
	gRPC "google.golang.org/grpc"
)

type HyperServer struct {
	Hyper hyper.Interface
	Addr  string

	Log *zerolog.Logger
	WG  *sync.WaitGroup

	proto.UnimplementedHyperServer
}

func (h *HyperServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, h.Log, h.WG, func(s *gRPC.Server) {
		proto.RegisterHyperServer(s, h)
	}, h.Addr)
}
