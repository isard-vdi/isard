package orchestrator

import (
	"context"
	"errors"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/orchestrator/log"
	"gitlab.com/isard/isardvdi/orchestrator/model"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"

	"gitlab.com/isard/isardvdi-cli/pkg/client"

	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var ErrTimeout = errors.New("operation timeout")

type Orchestrator struct {
	director director.Director

	dryRun            bool
	pollingInterval   time.Duration
	operationsTimeout time.Duration

	db            r.QueryExecutor
	operationsCli operationsv1.OperationsServiceClient
	apiCli        client.Interface

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

	DB            r.QueryExecutor
	Director      director.Director
	OperationsCli operationsv1.OperationsServiceClient

	APICli client.Interface
}

func New(cfg *NewOrchestratorOpts) *Orchestrator {
	log2 := cfg.Log.With().Str("director", cfg.Director.String()).Logger()

	return &Orchestrator{
		director: cfg.Director,

		dryRun:            cfg.DryRun,
		pollingInterval:   cfg.PollingInterval,
		operationsTimeout: cfg.OperationsTimeout,

		db:            cfg.DB,
		operationsCli: cfg.OperationsCli,
		apiCli:        cfg.APICli,

		log: &log2,
		wg:  cfg.WG,
	}
}

func (o *Orchestrator) Start(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			// TODO: Wait for operations to be stopped
			o.wg.Done()
			return

		default:
			hypers, err := model.GetHypervisors(ctx, o.db)
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

				create, destroy, err := o.director.NeedToScaleHypervisors(ctx, operationsHypers.Hypervisors, hypers)
				if err != nil {
					o.log.Error().Err(err).Msg("check if there are hypervisors that need to scale")
					continue
				}

				timeout, cancel := context.WithTimeout(ctx, o.operationsTimeout)
				defer cancel()

				if create != nil {
					if o.dryRun {
						o.log.Info().Bool("DRY_RUN", true).Str("id", create.Id).Msg("create hypervisor")

					} else {
						go o.createHypervisor(timeout, create)
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

			if err := o.director.ExtraOperations(ctx, hypers); err != nil {
				o.log.Error().Err(err).Msg("execute extra orchestrator operations")
				continue
			}

			time.Sleep(o.pollingInterval)
		}
	}
}
