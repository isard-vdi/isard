package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/haproxy-bastion-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-bastion-sync/haproxy"
	haproxybastionsync "gitlab.com/isard/isardvdi/haproxy-bastion-sync/haproxy-bastion-sync"
	"gitlab.com/isard/isardvdi/haproxy-bastion-sync/transport/grpc"

	"gitlab.com/isard/isardvdi/pkg/log"
)

func main() {
	cfg := cfg.New()

	log := log.New("haproxy-bastion-sync", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	haproxy, err := haproxy.NewHAProxy(log, cfg.Haproxy.SocketAddress)
	if err != nil {
		log.Fatal().Err(err).Msg("connect to HAProxy admin stats socket")
	}

	haproxybastionsync := haproxybastionsync.Init(log, cfg, haproxy)

	grpc := grpc.NewHAProxyBastionSyncServer(log, &wg, cfg.GRPC, haproxybastionsync)

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
