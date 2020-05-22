package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"

	"github.com/isard-vdi/isard/desktop-builder/cfg"
	"github.com/isard-vdi/isard/desktop-builder/desktopbuilder"
	"github.com/isard-vdi/isard/desktop-builder/env"
	"github.com/isard-vdi/isard/desktop-builder/transport/grpc"

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

	db, err := desktopbuilder.New(env)
	if err != nil {
		env.Sugar.Fatalw("connect to the hypervisor",
			"err", err,
		)
	}
	env.DesktopBuilder = db

	ctx, cancel := context.WithCancel(context.Background())

	go grpc.Serve(ctx, env)
	env.WG.Add(1)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	select {
	case <-stop:
		fmt.Println("")
		env.Sugar.Info("stoping desktop-builder...")

		cancel()

		env.WG.Wait()
	}
}
