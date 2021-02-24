package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/controller/cfg"
	"gitlab.com/isard/isardvdi/controller/controller"
	"gitlab.com/isard/isardvdi/controller/transport/grpc"
	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/pkg/redis"
)

func main() {
	cfg := cfg.New()

	log := log.New("controller", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	redis := redis.New(cfg.Redis.Cluster, cfg.Redis.Host, cfg.Redis.Port, cfg.Redis.Usr, cfg.Redis.Pwd)
	if err := redis.Ping(ctx).Err(); err != nil {
		log.Fatal().Err(err).Msg("connect to redis")
	}

	controller, err := controller.New(ctx, cfg, redis)
	if err != nil {
		log.Fatal().Err(err).Msg("create controller")
	}

	grpc := &grpc.ControllerServer{
		Controller: controller,
		Addr:       fmt.Sprintf("%s:%d", cfg.GRPC.Host, cfg.GRPC.Port),
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
