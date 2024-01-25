package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/transport/http"
	"gitlab.com/isard/isardvdi/pkg/db"
	"gitlab.com/isard/isardvdi/pkg/log"
)

func main() {
	cfg := cfg.New()

	log := log.New("authentication", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	db, err := db.New(cfg.DB)
	if err != nil {
		log.Fatal().Err(err).Msg("connect to the database")
	}

	authentication := authentication.Init(cfg, log, db)

	_ = authentication.Healthcheck()

	go http.Serve(ctx, &wg, log, cfg.HTTP.Addr(), authentication)
	wg.Add(1)

	log.Info().Strs("providers", authentication.Providers()).Msg("service started")

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()
}
