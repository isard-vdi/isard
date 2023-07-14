package orchestrator

import (
	"context"
	"errors"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/log"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	checkv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/check/v1"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"

	"gitlab.com/isard/isardvdi-sdk-go"

	"github.com/rs/zerolog"
)

var ErrTimeout = errors.New("operation timeout")

type Orchestrator struct {
	director director.Director

	dryRun            bool
	pollingInterval   time.Duration
	operationsTimeout time.Duration

	operationsCli operationsv1.OperationsServiceClient
	checkCfg      cfg.Check
	checkCli      checkv1.CheckServiceClient
	apiAddress    string
	apiSecret     string
	apiCli        isardvdi.Interface

	scaleMux sync.Mutex
	scaling  bool

	log *zerolog.Logger
	wg  *sync.WaitGroup
}

type NewOrchestratorOpts struct {
	Log *zerolog.Logger
	WG  *sync.WaitGroup

	DryRun            bool
	PollingInterval   time.Duration
	OperationsTimeout time.Duration

	Director      director.Director
	OperationsCli operationsv1.OperationsServiceClient

	CheckCfg cfg.Check
	CheckCli checkv1.CheckServiceClient

	APIAddress string
	APISecret  string
	APICli     isardvdi.Interface
}

func New(cfg *NewOrchestratorOpts) *Orchestrator {
	log2 := cfg.Log.With().Str("director", cfg.Director.String()).Logger()

	return &Orchestrator{
		director: cfg.Director,

		dryRun:            cfg.DryRun,
		pollingInterval:   cfg.PollingInterval,
		operationsTimeout: cfg.OperationsTimeout,

		operationsCli: cfg.OperationsCli,
		checkCfg:      cfg.CheckCfg,
		checkCli:      cfg.CheckCli,
		apiAddress:    cfg.APIAddress,
		apiSecret:     cfg.APISecret,
		apiCli:        cfg.APICli,

		log: &log2,
		wg:  cfg.WG,
	}
}

func (o *Orchestrator) Start(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			o.wg.Done()
			return

		default:
			time.Sleep(o.pollingInterval)

			hypers, err := o.apiCli.OrchestratorHypervisorList(ctx)
			if err != nil {
				o.log.Error().Err(err).Msg("get hypervisors")
				continue
			}

			if !o.scaling {
				operationsHypers, err := o.operationsCli.ListHypervisors(ctx, &operationsv1.ListHypervisorsRequest{})
				if err != nil {
					o.log.Error().Err(err).Msg("list the hypervisors of the operations service")
					continue
				}

				o.log.Debug().Array("isard_hypervisors", log.NewModelHypervisors(hypers)).Array("infrastructure_hypervisors", log.NewOperationsV1ListHypervisorsResponse(operationsHypers)).Msg("infrastructure state")

				create, destroy, removeDeadRow, addDeadRow, err := o.director.NeedToScaleHypervisors(ctx, operationsHypers.Hypervisors, hypers)
				if err != nil {
					o.log.Error().Err(err).Msg("check if there are hypervisors that need to scale")
					continue
				}

				timeout, cancel := context.WithTimeout(ctx, o.operationsTimeout)
				defer cancel()

				if removeDeadRow != "" {
					if o.dryRun {
						o.log.Info().Bool("DRY_RUN", true).Str("id", removeDeadRow).Msg("cancel hypervisor destruction")

					} else {
						go o.removeHypervisorFromDeadRow(timeout, removeDeadRow)
					}
				}

				if create != nil {
					if o.dryRun {
						o.log.Info().Bool("DRY_RUN", true).Str("id", create.Id).Msg("create hypervisor")

					} else {
						go o.createHypervisor(timeout, create)
					}
				}

				if addDeadRow != "" {
					if o.dryRun {
						o.log.Info().Bool("DRY_RUN", true).Str("id", addDeadRow).Msg("set hypervisor to destroy")

					} else {
						go o.addHypervisorToDeadRow(timeout, addDeadRow)
					}
				}

				if destroy != nil {
					if o.dryRun {
						o.log.Info().Bool("DRY_RUN", true).Str("id", destroy.Id).Msg("destroy hypervisor")

					} else {
						go o.destroyHypervisor(timeout, destroy)
					}
				}
			}

			hypers, err = o.apiCli.OrchestratorHypervisorList(ctx)
			if err != nil {
				o.log.Error().Err(err).Msg("get hypervisors")
				continue
			}

			if err := o.director.ExtraOperations(ctx, hypers); err != nil {
				o.log.Error().Err(err).Msg("execute extra orchestrator operations")
				continue
			}

		}
	}
}
