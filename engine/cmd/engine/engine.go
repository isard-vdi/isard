package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"

	"github.com/isard-vdi/isard/engine/cfg"
	"github.com/isard-vdi/isard/engine/env"
	"github.com/isard-vdi/isard/engine/transport/grpc"

	"go.uber.org/zap"
)

func main() {
	logger, err := zap.NewProduction()
	if err != nil {
		log.Fatalf("create logger: %v", err)
	}
	defer logger.Sync()

	env := &env.Env{
		Sugar: logger.Sugar(),
		Cfg: cfg.Cfg{
			GRPC: cfg.GRPC{
				Port: 1312,
			},
		},
	}

	ctx, cancel := context.WithCancel(context.Background())

	go grpc.Serve(ctx, env)
	env.WG.Add(1)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	select {
	case <-stop:
		fmt.Println("")
		env.Sugar.Info("stoping engine...")

		cancel()

		env.WG.Wait()
	}
}
