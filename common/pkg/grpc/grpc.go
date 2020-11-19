package grpc

import (
	"context"
	"net"
	"sync"

	"github.com/rs/zerolog"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// RequiredParams are the parameters that are required for a gRPC method
type RequiredParams map[string]interface{}

// Required returns an error if a parameter is required and it not provided
func Required(r RequiredParams) error {
	for k, v := range r {
		if v == nil {
			return status.Errorf(codes.InvalidArgument, "parameter '%s' is required and not provided", k)
		}
	}

	return nil
}

func Serve(ctx context.Context, log *zerolog.Logger, wg *sync.WaitGroup, registerServer func(s *grpc.Server), addr string) {
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		log.Fatal().Err(err).Str("addr", addr).Msg("listen gRPC port")
	}

	s := grpc.NewServer()
	registerServer(s)

	// TODO: Reflection, health check

	log.Info().Str("addr", addr).Msg("serving through gRPC")

	go func() {
		if err := s.Serve(lis); err != nil {
			log.Fatal().Err(err).Str("addr", addr).Msg("serve gRPC")
		}
	}()

	<-ctx.Done()
	s.GracefulStop()
	wg.Done()
}
