package grpc

import (
	"context"
	"sync"

	"gitlab.com/isard/isardvdi/auth/authentication"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"

	"github.com/rs/zerolog"
	gRPC "google.golang.org/grpc"
)

type AuthServer struct {
	Authentication authentication.Interface
	Addr           string

	Log *zerolog.Logger
	WG  *sync.WaitGroup

	auth.UnimplementedAuthServer
}

func (a *AuthServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, a.Log, a.WG, func(s *gRPC.Server) {
		auth.RegisterAuthServer(s, a)
	}, a.Addr)
}
