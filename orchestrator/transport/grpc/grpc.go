package grpc

import (
	"context"
	"sync"

	"gitlab.com/isard/isardvdi/orchestrator/provider"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/proto/orchestrator"

	"github.com/rs/zerolog"
	gRPC "google.golang.org/grpc"
)

type OrchestratorServer struct {
	Provider provider.Provider
	Addr     string

	Log *zerolog.Logger
	WG  *sync.WaitGroup

	orchestrator.UnimplementedOrchestratorServer
}

func (o *OrchestratorServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, o.Log, o.WG, func(s *gRPC.Server) {
		orchestrator.RegisterOrchestratorServer(s, o)
	}, o.Addr)
}
