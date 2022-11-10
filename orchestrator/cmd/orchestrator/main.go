package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	apiCfg "gitlab.com/isard/isardvdi-cli/pkg/cfg"
	"gitlab.com/isard/isardvdi-cli/pkg/client"
	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	"gitlab.com/isard/isardvdi/pkg/db"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/log"
	"google.golang.org/grpc"
)

func main() {
	cfg := cfg.New()

	log := log.New("operations", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	db, err := db.New(cfg.DB)
	if err != nil {
		log.Fatal().Err(err).Msg("connect to the database")
	}

	api, err := client.NewClient(&apiCfg.Cfg{
		Host: "http://isard-api:5000",
	})
	if err != nil {
		log.Fatal().Err(err).Msg("create API client")
	}

	var dir director.Director
	switch cfg.Orchestrator.Director {
	case director.DirectorTypeRata:
		dir = director.NewRata(cfg.Orchestrator, log, api)

	default:
		log.Fatal().Str("director", cfg.Orchestrator.Director).Strs("available_directors", director.Available).Msg("unknown director type!")
	}

	opts := []grpc.DialOption{grpc.WithInsecure()}
	operationsConn, err := grpc.DialContext(ctx, cfg.Orchestrator.OperationsAddress, opts...)
	if err != nil {
		log.Fatal().Str("addr", cfg.Orchestrator.OperationsAddress).Err(err).Msg("dial gRPC operations service")
	}
	defer operationsConn.Close()

	operationsCli := operationsv1.NewOperationsServiceClient(operationsConn)

	orchestrator := orchestrator.New(&orchestrator.NewOrchestratorOpts{
		Log:               log,
		WG:                &wg,
		PollingInterval:   cfg.Orchestrator.PollingInterval,
		OperationsTimeout: cfg.Orchestrator.OperationsTimeout,
		DB:                db,
		Director:          dir,
		OperationsCli:     operationsCli,
		APISecret:         cfg.Orchestrator.APISecret,
		APICli:            api,
	})
	go orchestrator.Start(ctx)
	wg.Add(1)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()
}
