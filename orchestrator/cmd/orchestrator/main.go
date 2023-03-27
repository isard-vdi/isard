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
	checkv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/check/v1"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/jwt"
	"gitlab.com/isard/isardvdi/pkg/log"
	"google.golang.org/grpc"
)

func main() {
	cfg := cfg.New()

	log := log.New("orchestrator", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	api, err := client.NewClient(&apiCfg.Cfg{
		Host: cfg.Orchestrator.APIAddress,
	})
	if err != nil {
		log.Fatal().Err(err).Msg("create API client")
	}

	api.SetBeforeRequestHook(func(c *client.Client) error {
		tkn, err := jwt.SignAPIJWT(cfg.Orchestrator.APISecret)
		if err != nil {
			return fmt.Errorf("sign JWT token for calling the API: %w", err)
		}

		c.SetToken(tkn)

		return nil
	})

	var dir director.Director
	switch cfg.Orchestrator.Director {
	case director.DirectorTypeRata:
		dir = director.NewRata(cfg.Orchestrator.DirectorRata, cfg.DryRun, log, api)

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

	checkConn, err := grpc.DialContext(ctx, cfg.Orchestrator.CheckAddress, opts...)
	if err != nil {
		log.Fatal().Str("addr", cfg.Orchestrator.CheckAddress).Err(err).Msg("dial gRPC check service")
	}
	defer checkConn.Close()

	checkCli := checkv1.NewCheckServiceClient(checkConn)

	orchestrator := orchestrator.New(&orchestrator.NewOrchestratorOpts{
		Log:               log,
		WG:                &wg,
		DryRun:            cfg.DryRun,
		PollingInterval:   cfg.Orchestrator.PollingInterval,
		OperationsTimeout: cfg.Orchestrator.OperationsTimeout,
		Director:          dir,
		OperationsCli:     operationsCli,
		CheckCfg:          cfg.Orchestrator.Check,
		CheckCli:          checkCli,
		APIAddress:        cfg.Orchestrator.APIAddress,
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
