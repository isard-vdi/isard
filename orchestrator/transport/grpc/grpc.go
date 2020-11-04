package grpc

import (
	"context"
	"sync"

	"gitlab.com/isard/isardvdi/common/pkg/grpc"
	"gitlab.com/isard/isardvdi/orchestrator/pkg/proto"
	"gitlab.com/isard/isardvdi/orchestrator/provider"

	"github.com/rs/zerolog"
	gRPC "google.golang.org/grpc"
)

type OrchestratorServer struct {
	Provider provider.Provider
	Addr     string

	Log *zerolog.Logger
	WG  *sync.WaitGroup

	proto.UnimplementedOrchestratorServer
}

func (o *OrchestratorServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, o.Log, o.WG, func(s *gRPC.Server) {
		proto.RegisterOrchestratorServer(s, o)
	}, o.Addr)
}
