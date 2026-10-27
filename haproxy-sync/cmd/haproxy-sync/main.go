package main

import (
	"context"
	"os"
	"os/signal"
	"sync"
	"syscall"

	"gitlab.com/isard/isardvdi/haproxy-sync/acme"
	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/haproxy-sync/transport/grpc"

	"gitlab.com/isard/isardvdi/pkg/log"
)

func main() {
	// SIGHUP terminates the process until it is handled.
	reloaded := make(chan os.Signal, 1)
	signal.Notify(reloaded, syscall.SIGHUP)

	cfg := cfg.New()

	log := log.New("haproxy-sync", cfg.Log.Level)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	var wg sync.WaitGroup

	haproxy := haproxy.NewHAProxy(log, cfg.HAProxy.SocketAddress)
	if err := haproxy.WaitReady(ctx, cfg.HAProxy.StartupTimeout); err != nil {
		log.Fatal().Err(err).Msg("wait for the HAProxy admin socket to become ready")
	}

	acme := acme.NewACME(log, cfg.HAProxy.Domains.CertsPath)

	haproxysync := haproxysync.Init(log, cfg.HAProxy, haproxy, acme)

	grpc := grpc.NewHAProxySyncServer(log, &wg, cfg.GRPC, haproxysync)

	go grpc.Serve(ctx)
	wg.Add(1)

	wg.Go(func() {
		for {
			select {
			case <-ctx.Done():
				return

			case <-reloaded:
				if err := haproxysync.Restore(ctx); err != nil {
					log.Error().Err(err).Msg("restore the HAProxy state")
				}
			}
		}
	})

	log.Info().Msg("service started")

	<-ctx.Done()
	log.Info().Msg("stopping service")

	stop()
	wg.Wait()
}
