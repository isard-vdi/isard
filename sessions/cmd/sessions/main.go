package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/pkg/redis"
	"gitlab.com/isard/isardvdi/sessions/cfg"
	"gitlab.com/isard/isardvdi/sessions/sessions"
	"gitlab.com/isard/isardvdi/sessions/transport/grpc"
)

func main() {
	cfg := cfg.New()

	log := log.New("sessions", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	redis, err := redis.New(ctx, cfg.Redis)
	if err != nil {
		log.Fatal().Err(err).Msg("could not connect to redis")
	}

	sessions := sessions.Init(ctx, log, cfg.Sessions, redis)

	grpc := grpc.NewSessionsServer(log, &wg, cfg.GRPC.Addr(), sessions)

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
