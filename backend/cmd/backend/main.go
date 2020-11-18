//go:generate go run github.com/99designs/gqlgen
package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/backend/cfg"
	"gitlab.com/isard/isardvdi/backend/transport/http"

	"gitlab.com/isard/isardvdi/common/pkg/log"
)

func main() {
	cfg := cfg.New()

	log := log.New("backend", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	http := &http.BackendServer{
		Addr: fmt.Sprintf("%s:%d", cfg.GraphQL.Host, cfg.GraphQL.Port),
		Log:  log,
		WG:   &wg,
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
