package grpc

import (
	"context"
	"fmt"
	"net"

	"github.com/isard-vdi/isard/hyper/env"
	"github.com/isard-vdi/isard/hyper/hyper"
	"github.com/isard-vdi/isard/hyper/pkg/proto"

	gRPC "google.golang.org/grpc"
)

// API is the version for the gRPC API
const API = "v1.0.0"

// HyperServer implements the gRPC server
type HyperServer struct {
	env   *env.Env
	hyper hyper.Interface
}

// Serve starts the Hyper gRPC server
func Serve(ctx context.Context, env *env.Env, hyper hyper.Interface) {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", env.Cfg.GRPC.Port))
	if err != nil {
		env.Sugar.Fatalw("listen gRPC port",
			"err", err,
			"port", env.Cfg.GRPC.Port,
		)
	}

	srv := &HyperServer{env, hyper}
	s := gRPC.NewServer()
	proto.RegisterHyperServer(s, srv)

	env.Sugar.Infow("hyper gRPC serving",
		"port", env.Cfg.GRPC.Port,
	)
	go func() {
		if err = s.Serve(lis); err != nil {
			if err != gRPC.ErrServerStopped {
				env.Sugar.Fatalw("serve hyper gRPC",
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
