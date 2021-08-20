package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/migrations/cfg"
	"gitlab.com/isard/isardvdi/migrations/migrations"
	"gitlab.com/isard/isardvdi/migrations/transport/grpc"
	"gitlab.com/isard/isardvdi/pkg/log"
)

func main() {
	config := cfg.New()

	log := log.New(cfg.ServiceName, config.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	migrations := migrations.NewMigrations(config.Redis)

	grpc := &grpc.MigrationsServiceServer{
		Migrations: migrations,
		Addr:       config.GRPC.Addr(),
		Log:        log,
		WG:         &wg,
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
