package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"gitlab.com/isard/isardvdi/pkg/haproxy-bastion-sync/cfg"
	"gitlab.com/isard/isardvdi/pkg/haproxy-bastion-sync/haproxy"
	grpcTransport "gitlab.com/isard/isardvdi/pkg/haproxy-bastion-sync/transport/grpc"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

func main() {
	// Configure logging
	zerolog.TimeFieldFormat = zerolog.TimeFormatUnix
	log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr})

	// Load configuration
	c := cfg.New()

	// Set log level
	level, err := zerolog.ParseLevel(c.Log.Level)
	if err != nil {
		log.Fatal().Err(err).Msg("parse log level")
	}
	zerolog.SetGlobalLevel(level)

	log.Info().Msg("starting haproxy-bastion-sync service")

	// Create context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	var wg sync.WaitGroup

	// Initialize HAProxy socket
	socket := haproxy.NewSocket(c.Maps.SocketPath, &log.Logger)
	log.Info().Str("socket", c.Maps.SocketPath).Msg("connecting to HAProxy socket")

	// Connect to HAProxy with retry
	if err := connectWithRetry(socket, 5, 2*time.Second); err != nil {
		log.Fatal().Err(err).Msg("failed to connect to HAProxy socket")
	}

	// Initialize map store with empty maps (will be populated via gRPC)
	store := haproxy.NewMapStore(c.Maps.SubdomainsPath, c.Maps.IndividualPath, &log.Logger)

	// Initialize syncer
	syncer := haproxy.NewSyncer(socket, store, c.Maps.SubdomainsPath, c.Maps.IndividualPath, &log.Logger)

	log.Info().Msg("waiting for initial domain sync via gRPC from API...")

	// Start gRPC server
	wg.Add(1)
	server := grpcTransport.NewHaproxyBastionServer(syncer, store, c.GRPC.Addr(), &log.Logger, &wg)
	go server.Serve(ctx)

	log.Info().Str("addr", c.GRPC.Addr()).Msg("haproxy-bastion-sync service started")

	// Handle signals for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	<-sigChan
	log.Info().Msg("shutdown signal received, stopping service")

	// Cancel context to stop gRPC server
	cancel()

	// Wait for gRPC server to stop (with timeout)
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		log.Info().Msg("service stopped gracefully")
	case <-time.After(10 * time.Second):
		log.Warn().Msg("shutdown timeout exceeded, forcing exit")
	}

	// Close HAProxy socket
	if err := socket.Close(); err != nil {
		log.Error().Err(err).Msg("failed to close HAProxy socket")
	}
}

// connectWithRetry attempts to connect to HAProxy socket with retries
func connectWithRetry(socket *haproxy.Socket, maxRetries int, delay time.Duration) error {
	var lastErr error
	for i := 0; i < maxRetries; i++ {
		if err := socket.Connect(); err != nil {
			lastErr = err
			log.Warn().
				Err(err).
				Int("attempt", i+1).
				Int("max_retries", maxRetries).
				Msg("failed to connect to HAProxy socket, retrying")
			time.Sleep(delay)
			continue
		}
		return nil
	}
	return fmt.Errorf("failed after %d attempts: %w", maxRetries, lastErr)
}
