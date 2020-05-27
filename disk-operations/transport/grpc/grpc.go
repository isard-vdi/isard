package grpc

import (
	"context"
	"fmt"
	"net"

	"github.com/isard-vdi/isard/disk-operations/diskoperations"
	"github.com/isard-vdi/isard/disk-operations/env"
	"github.com/isard-vdi/isard/disk-operations/pkg/proto"

	gRPC "google.golang.org/grpc"
)

// API is the version for the gRPC API
const API = "v1.0.0"

// DiskOperationsServer implements the gRPC server
type DiskOperationsServer struct {
	env            *env.Env
	diskoperations *diskoperations.DiskOperations
}

// Serve starts the DiskOperations gRPC server
func Serve(ctx context.Context, env *env.Env, diskoperations *diskoperations.DiskOperations) {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", env.Cfg.GRPC.Port))
	if err != nil {
		env.Sugar.Fatalw("listen gRPC port",
			"err", err,
			"port", env.Cfg.GRPC.Port,
		)
	}

	srv := &DiskOperationsServer{env, diskoperations}
	s := gRPC.NewServer()
	proto.RegisterDiskOperationsServer(s, srv)

	env.Sugar.Infow("DiskOperations gRPC serving",
		"port", env.Cfg.GRPC.Port,
	)
	go func() {
		if err = s.Serve(lis); err != nil {
			if err != gRPC.ErrServerStopped {
				env.Sugar.Fatalw("serve DiskOperations gRPC",
					"err", err,
					"port", env.Cfg.GRPC.Port,
				)
			}
		}
	}()

	select {
	case <-ctx.Done():
		s.Stop()
		env.WG.Done()
	}
}
