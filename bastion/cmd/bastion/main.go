package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/bastion/cfg"
	"gitlab.com/isard/isardvdi/bastion/model"
	"gitlab.com/isard/isardvdi/bastion/transport/http"
	"gitlab.com/isard/isardvdi/bastion/transport/ssh"
	"gitlab.com/isard/isardvdi/pkg/db"
	"gitlab.com/isard/isardvdi/pkg/log"
)

func main() {
	cfg := cfg.New()

	log := log.New("bastion", cfg.Log.Level)

	dbSess, err := db.New(cfg.DB)
	if err != nil {
		log.Fatal().Err(err).Msg("create DB connection")
	}

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	cfgLog := log.With().Str("config", "bastion").Logger()
	cfgWatcher := db.NewWatcher(&cfgLog, 30*time.Second, 0, func(ctx context.Context) (model.Config, error) {
		cfg := model.Config{}
		if err := cfg.Load(ctx, dbSess); err != nil {
			return model.Config{}, err
		}

		return cfg, nil
	})

	if err := cfgWatcher.Start(ctx, &wg); err != nil {
		log.Fatal().Err(err).Msg("load initial bastion configuration")
	}

	httpLog := log.With().Str("transport", "http").Logger()
	wg.Go(func() {
		http.Serve(ctx, &httpLog, dbSess, cfgWatcher, cfg.HTTP)
	})

	sshLog := log.With().Str("transport", "ssh").Logger()
	wg.Go(func() {
		ssh.Serve(ctx, &sshLog, dbSess, cfgWatcher, cfg.SSH)
	})

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()
}
