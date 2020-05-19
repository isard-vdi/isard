package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"

	"github.com/isard-vdi/isard/hyper-stats/cfg"
	"github.com/isard-vdi/isard/hyper-stats/env"
	"github.com/isard-vdi/isard/hyper-stats/pkg/redis"

	"go.uber.org/zap"
)

func main() {
	logger, err := zap.NewProduction()
	if err != nil {
		log.Fatalf("create logger: %v", err)
	}
	defer logger.Sync()
	sugar := logger.Sugar()

	env := &env.Env{
		Sugar: sugar,
		Cfg:   cfg.Init(sugar),
	}

	var cancel context.CancelFunc
	env.Ctx, cancel = context.WithCancel(context.Background())

	redis.Init(env)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	select {
	case <-stop:
		fmt.Println("")
		env.Sugar.Info("stoping hyper-stats...")

		cancel()

		env.WG.Wait()

		env.Redis.Close()
	}
}
