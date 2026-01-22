package grpc

import (
	"context"
	"net"
	"sync"
	"time"

	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi/pkg/cfg"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"
)

func Serve(ctx context.Context, log *zerolog.Logger, wg *sync.WaitGroup, desc *grpc.ServiceDesc, srv healthCheckableServer, cfg cfg.GRPC) {
	grpcLogger := log.With().Str("grpc_service_name", desc.ServiceName).Logger()
	log = &grpcLogger

	lis, err := net.Listen("tcp", cfg.Addr())
	if err != nil {
		log.Fatal().Err(err).Str("addr", cfg.Addr()).Msg("listen gRPC address")
	}

	s := grpc.NewServer(
		grpc.UnaryInterceptor(newUnaryInterceptorLogger(log)),
	)

	// TODO: testEmbeddedByValue

	s.RegisterService(desc, srv)
	registerHealthcheck(ctx, log, s, desc, srv, cfg.HealthCheckInterval)
	reflection.Register(s)

	go func() {
		if err := s.Serve(lis); err != nil {
			log.Fatal().Err(err).Str("addr", cfg.Addr()).Msg("serve gRPC")
		}
	}()

	log.Info().Str("addr", cfg.Addr()).Msg("serving through gRPC")

	<-ctx.Done()

	s.GracefulStop()
	wg.Done()
}

type healthCheckableServer interface {
	Check(ctx context.Context) error
}

func registerHealthcheck(ctx context.Context, log *zerolog.Logger, registrar grpc.ServiceRegistrar, desc *grpc.ServiceDesc, srv healthCheckableServer, interval time.Duration) {
	health := health.NewServer()
	healthpb.RegisterHealthServer(registrar, health)

	go func() {
		for {
			select {
			case <-ctx.Done():
				health.SetServingStatus(desc.ServiceName, healthpb.HealthCheckResponse_NOT_SERVING)
				return

			default:
				if err := srv.Check(ctx); err != nil {
					log.Warn().Err(err).Msg("healthcheck failed")

					health.SetServingStatus(desc.ServiceName, healthpb.HealthCheckResponse_NOT_SERVING)
				} else {
					log.Debug().Msg("healthcheck succeeded")
					health.SetServingStatus(desc.ServiceName, healthpb.HealthCheckResponse_SERVING)
				}

				time.Sleep(interval)
			}
		}
	}()
}
