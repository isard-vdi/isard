package grpc

import (
	"context"
	"sync"

	"gitlab.com/isard/isardvdi/diskoperations/diskoperations"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	proto "gitlab.com/isard/isardvdi/pkg/proto/diskoperations"

	"github.com/rs/zerolog"
	gRPC "google.golang.org/grpc"
)

type DiskOperationsServer struct {
	DiskOperations diskoperations.Interface
	Addr           string

	Log *zerolog.Logger
	WG  *sync.WaitGroup

	proto.UnimplementedDiskOperationsServer
}

func (d *DiskOperationsServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, d.Log, d.WG, func(s *gRPC.Server) {
		proto.RegisterDiskOperationsServer(s, d)
	}, d.Addr)
}
