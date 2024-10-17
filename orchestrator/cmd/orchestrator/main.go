package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	checkv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/check/v1"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/jwt"
	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/pkg/sdk"
)

func main() {
	cfg := cfg.New()

	log := log.New("orchestrator", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	api, err := sdk.NewClient(&sdk.Cfg{
		Host: cfg.Orchestrator.APIAddress,
	})
	if err != nil {
		log.Fatal().Err(err).Msg("create API client")
	}

	api.SetBeforeRequestHook(func(c *sdk.Client) error {
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

	case director.DirectorTypeChamaleon:
		dir = director.NewChamaleon(log, api)

	default:
		log.Fatal().Str("director", cfg.Orchestrator.Director).Strs("available_directors", director.Available).Msg("unknown director type!")
	}

	operationsCli, operationsConn, err := grpc.NewClient(ctx, operationsv1.NewOperationsServiceClient, cfg.Orchestrator.OperationsAddress)
	if err != nil {
		log.Fatal().Str("addr", cfg.Orchestrator.OperationsAddress).Err(err).Msg("create the operations service client")
	}
	defer operationsConn.Close()

	checkCli, checkConn, err := grpc.NewClient(ctx, checkv1.NewCheckServiceClient, cfg.Orchestrator.CheckAddress)
	if err != nil {
		log.Fatal().Str("addr", cfg.Orchestrator.CheckAddress).Err(err).Msg("create the check service client")
	}
	defer checkConn.Close()

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
