package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/bastion/cfg"
	"gitlab.com/isard/isardvdi/bastion/transport/http"
	"gitlab.com/isard/isardvdi/bastion/transport/ssh"
	"gitlab.com/isard/isardvdi/pkg/db"
	"gitlab.com/isard/isardvdi/pkg/log"
)

func main() {
	cfg := cfg.New()

	log := log.New("bastion", cfg.Log.Level)

	db, err := db.New(cfg.DB)
	if err != nil {
		log.Fatal().Err(err).Msg("create DB connection")
	}

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	httpLog := log.With().Str("transport", "http").Logger()
	go http.Serve(ctx, &wg, &httpLog, db, cfg.HTTP)
	wg.Add(1)

	sshLog := log.With().Str("transport", "ssh").Logger()
	go ssh.Serve(ctx, &wg, &sshLog, db, cfg.SSH)
	wg.Add(1)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()
}
