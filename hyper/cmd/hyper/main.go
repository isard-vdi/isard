package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/hyper/cfg"
	"gitlab.com/isard/isardvdi/hyper/hyper"
	"gitlab.com/isard/isardvdi/hyper/transport/grpc"

	"gitlab.com/isard/isardvdi/common/pkg/log"
)

func main() {
	cfg := cfg.New()

	log := log.New("hyper", cfg.Log.Level)

	h, err := hyper.New("")
	if err != nil {
		log.Fatal().Err(err).Msg("connect to the hypervisor")
	}
	defer h.Close()

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	grpc := &grpc.HyperServer{
		Hyper: h,
		Addr:  fmt.Sprintf("%s:%d", cfg.GRPC.Host, cfg.GRPC.Port),
		Log:   log,
		WG:    &wg,
	}
	go grpc.Serve(ctx)
	wg.Add(1)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()
}
