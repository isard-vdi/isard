package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"

	"github.com/isard-vdi/isard/hyper/cfg"
	"github.com/isard-vdi/isard/hyper/env"
	"github.com/isard-vdi/isard/hyper/hyper"
	"github.com/isard-vdi/isard/hyper/transport/grpc"

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

	h, err := hyper.New(env, "")
	if err != nil {
		env.Sugar.Fatalw("connect to the hypervisor",
			"err", err,
		)
	}
	defer h.Close()

	ctx, cancel := context.WithCancel(context.Background())

	go grpc.Serve(ctx, env, h)
	env.WG.Add(1)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	select {
	case <-stop:
		fmt.Println("")
		env.Sugar.Info("stoping hyper...")

		cancel()

		env.WG.Wait()
	}
}
