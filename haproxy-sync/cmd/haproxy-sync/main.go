package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/haproxy-sync/acme"
	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/haproxy-sync/transport/grpc"

	"gitlab.com/isard/isardvdi/pkg/log"
)

func main() {
	cfg := cfg.New()

	log := log.New("haproxy-sync", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	haproxy, err := haproxy.NewHAProxy(log, cfg.HAProxy.SocketAddress)
	if err != nil {
		log.Fatal().Err(err).Msg("connect to HAProxy admin stats socket")
	}

	acme := acme.NewACME(log, cfg.HAProxy.Domains.CertsPath)

	haproxysync := haproxysync.Init(log, cfg.HAProxy, haproxy, acme)

	grpc := grpc.NewHAProxySyncServer(log, &wg, cfg.GRPC, haproxysync)

	go grpc.Serve(ctx)
	wg.Add(1)

	log.Info().Msg("service started")

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()
}
