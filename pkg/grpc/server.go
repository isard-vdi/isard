package grpc

import (
	"context"
	"net"
	"sync"

	"github.com/rs/zerolog"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

func Serve(ctx context.Context, log *zerolog.Logger, wg *sync.WaitGroup, registerServer func(s *grpc.Server), addr string) {
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		log.Fatal().Err(err).Str("addr", addr).Msg("listen gRPC address")
	}

	s := grpc.NewServer()
	registerServer(s)

	reflection.Register(s)

	// TODO: healthcheck

	go func() {
		if err := s.Serve(lis); err != nil {
			log.Fatal().Err(err).Str("addr", addr).Msg("serve gRPC")
		}
	}()

	log.Info().Str("addr", addr).Msg("serving through gRPC")

	<-ctx.Done()

	s.GracefulStop()
	wg.Done()
}
