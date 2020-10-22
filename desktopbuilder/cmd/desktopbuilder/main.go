package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/desktopbuilder/cfg"
	"gitlab.com/isard/isardvdi/desktopbuilder/desktopbuilder"
	"gitlab.com/isard/isardvdi/desktopbuilder/transport/grpc"

	"gitlab.com/isard/isardvdi/common/pkg/db"
	"gitlab.com/isard/isardvdi/common/pkg/log"
)

func main() {
	cfg := cfg.New()
	log := log.New("desktopbuilder", cfg.Log.Level)

	db, err := db.New(fmt.Sprintf("%s:%d", cfg.DB.Host, cfg.DB.Port), cfg.DB.Usr, cfg.DB.Pwd, cfg.DB.DB)
	if err != nil {
		log.Fatal().Err(err).Msg("connect to the database")
	}

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	d := desktopbuilder.New(db)

	grpc := &grpc.DesktopBuilderServer{
		DesktopBuilder: d,
		Addr:           fmt.Sprintf("%s:%d", cfg.GRPC.Host, cfg.GRPC.Port),
		Log:            log,
		WG:             &wg,
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
