package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/diskoperations/cfg"
	"gitlab.com/isard/isardvdi/diskoperations/diskoperations"
	"gitlab.com/isard/isardvdi/diskoperations/storage"
	"gitlab.com/isard/isardvdi/diskoperations/transport/grpc"
	"gitlab.com/isard/isardvdi/pkg/db"
	"gitlab.com/isard/isardvdi/pkg/log"
)

func main() {
	cfg := cfg.New()

	log := log.New("diskoperations", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	db, err := db.New(fmt.Sprintf("%s:%d", cfg.DB.Host, cfg.DB.Port), cfg.DB.Usr, cfg.DB.Pwd, cfg.DB.DB)
	if err != nil {
		log.Fatal().Err(err).Msg("connect to the database")
	}

	storage, err := storage.New(cfg.Storage.Driver)
	if err != nil {
		log.Fatal().Err(err)
	}

	diskoperations := diskoperations.New(db, storage, cfg.Storage.BasePath)

	grpc := &grpc.DiskOperationsServer{
		DiskOperations: diskoperations,
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
