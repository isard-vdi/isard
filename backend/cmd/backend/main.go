package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/backend/auth"
	"gitlab.com/isard/isardvdi/backend/cfg"
	"gitlab.com/isard/isardvdi/backend/transport/http"

	"gitlab.com/isard/isardvdi/common/pkg/db"
	"gitlab.com/isard/isardvdi/common/pkg/log"
	"gitlab.com/isard/isardvdi/common/pkg/redis"
)

func main() {
	cfg := cfg.New()

	log := log.New("backend", cfg.Log.Level)

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

	auth, err := auth.New(ctx, redis, db)
	if err != nil {
		log.Fatal().Err(err).Msg("create auth config")
	}

	http := &http.BackendServer{
		Addr: fmt.Sprintf("%s:%d", cfg.GraphQL.Host, cfg.GraphQL.Port),
		Log:  log,
		WG:   &wg,
	}
	go http.Serve(ctx, auth)
	wg.Add(1)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()
}
