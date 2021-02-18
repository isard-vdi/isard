package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/auth/authentication"
	"gitlab.com/isard/isardvdi/auth/cfg"
	"gitlab.com/isard/isardvdi/auth/transport/grpc"
	"gitlab.com/isard/isardvdi/auth/transport/http"
	"gitlab.com/isard/isardvdi/pkg/db"
	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/pkg/redis"
)

func main() {
	cfg := cfg.New()

	log := log.New("auth", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	redis := redis.New(cfg.Redis.Cluster, cfg.Redis.Host, cfg.Redis.Port, cfg.Redis.Usr, cfg.Redis.Pwd)
	if err := redis.Ping(ctx).Err(); err != nil {
		log.Fatal().Err(err).Msg("connect to redis")
	}

	db, err := db.New(fmt.Sprintf("%s:%d", cfg.DB.Host, cfg.DB.Port), cfg.DB.Usr, cfg.DB.Pwd, cfg.DB.DB)
	if err != nil {
		log.Fatal().Err(err).Msg("connect to the database")
	}

	authentication, err := authentication.New(ctx, redis, db)
	if err != nil {
		log.Fatal().Err(err).Msg("create authentication")
	}

	grpc := &grpc.AuthServer{
		Authentication: authentication,
		Addr:           fmt.Sprintf("%s:%d", cfg.GRPC.Host, cfg.GRPC.Port),
		Log:            log,
		WG:             &wg,
	}

	go grpc.Serve(ctx)
	wg.Add(1)

	http := &http.AuthServer{
		Authentication: authentication,
		Addr:           fmt.Sprintf("%s:%d", cfg.HTTP.Host, cfg.HTTP.Port),
		Log:            log,
		WG:             &wg,
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
