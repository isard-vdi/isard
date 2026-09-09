package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"

	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/model"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	"gitlab.com/isard/isardvdi/pkg/db"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	checkv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/check/v1"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
)

func main() {
	cfg := cfg.New()

	log := log.New("orchestrator", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	dbSess, err := db.New(cfg.DB)
	if err != nil {
		log.Fatal().Err(err).Msg("create DB connection")
	}

	cfgLog := log.With().Str("config", "orchestrator").Logger()
	cfgWatcher := db.NewWatcher(&cfgLog, cfg.Orchestrator.PollingInterval, 0, func(ctx context.Context) (model.Orchestrator, error) {
		c := model.Config{}
		if err := c.Load(ctx, dbSess); err != nil {
			return model.Orchestrator{}, err
		}

		return c.Orchestrator, nil
	})

	if err := cfgWatcher.Start(ctx, &wg); err != nil {
		log.Fatal().Err(err).Msg("load initial orchestrator configuration")
	}

	opts := []ogenclient.Option{
		ogenclient.WithUserAgent("isardvdi-orchestrator"),
		ogenclient.WithIgnoreCerts(),
	}

	httpClient := ogenclient.NewHTTPClient(opts...)
	api, err := apiv4.NewClient(
		cfg.Orchestrator.APIAddress,
		ogenclient.APIv4Source{Secret: cfg.Orchestrator.APISecret},
		apiv4.WithClient(httpClient),
	)
	if err != nil {
		log.Fatal().Err(err).Msg("create API client")
	}

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
		CfgWatcher:        cfgWatcher,
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
	wg.Go(func() {
		orchestrator.Start(ctx)
	})

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()
}
