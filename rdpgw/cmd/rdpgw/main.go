package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/rdpgw/cfg"
	"gitlab.com/isard/isardvdi/rdpgw/rdpgw"
	"gitlab.com/isard/isardvdi/rdpgw/transport/http"
)

func main() {
	cfg := cfg.New()

	log := log.New("rdpgw", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	http := &http.RDPGwServer{
		Gateway: rdpgw.Init(cfg),
		Addr:    cfg.HTTP.Addr(),
		Log:     log,
		WG:      &wg,
	}

	go http.Serve(ctx)
	wg.Add(1)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()
}
