package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"github.com/go-redis/redis/v8"
	"gitlab.com/isard/isardvdi/hyper/cfg"
	"gitlab.com/isard/isardvdi/hyper/hyper"
	"gitlab.com/isard/isardvdi/hyper/transport/grpc"

	"gitlab.com/isard/isardvdi/common/pkg/log"
)

func main() {
	cfg := cfg.New()

	log := log.New("hyper", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	redis := redis.NewClient(&redis.Options{
		Addr:     fmt.Sprintf("%s:%d", cfg.Redis.Host, cfg.Redis.Port),
		Username: cfg.Redis.Usr,
		Password: cfg.Redis.Pwd,
	})

	if err := redis.Ping(ctx).Err(); err != nil {
		log.Fatal().Err(err).Msg("connect to redis")
	}

	h, err := hyper.New(ctx, redis, cfg.Libvirt.URI, cfg.GRPC.Host)
	if err != nil {
		log.Fatal().Err(err).Msg("connect to the hypervisor")
	}
	defer h.Close()

	grpc := &grpc.HyperServer{
		Hyper: h,
		Addr:  fmt.Sprintf("%s:%d", cfg.GRPC.Host, cfg.GRPC.Port),
		Log:   log,
		WG:    &wg,
	}
	go grpc.Serve(ctx)
	wg.Add(1)

	if err := h.Ready(); err != nil {
		log.Fatal().Err(err).Msg("set hypervisor ready")
	}

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()
}
