package orchestrator

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/log"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/model"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	checkv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/check/v1"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"

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
	apiCli        apiv4.Invoker

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
	APICli     apiv4.Invoker
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

func (o *Orchestrator) listOrchestratorHypervisors(ctx context.Context) ([]*model.Hypervisor, error) {
	res, err := o.apiCli.AdminOrchestratorHypervisorsList(ctx)
	if err != nil {
		return nil, fmt.Errorf("list orchestrator hypervisors: %w", err)
	}

	if v, ok := res.(*apiv4.AdminOrchestratorHypervisorsListOKApplicationJSON); ok {
		return model.NewHypervisors([]apiv4.OrchestratorHypervisor(*v)), nil
	}

	return nil, ogenclient.AsAPIError(res)
}

func (o *Orchestrator) Start(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			o.wg.Done()
			return

		default:
			time.Sleep(o.pollingInterval)

			hypers, err := o.listOrchestratorHypervisors(ctx)
			if err != nil {
				o.log.Error().Err(err).Msg("get hypervisors")
				continue
			}

			if err := o.director.ExtraOperations(ctx, hypers); err != nil {
				o.log.Error().Err(err).Msg("execute extra orchestrator operations")
				continue
			}

			o.scaleMux.Lock()
			scaling := o.scaling
			o.scaleMux.Unlock()

			if !scaling {
				hypers, err := o.listOrchestratorHypervisors(ctx)
				if err != nil {
					o.log.Error().Err(err).Msg("get hypervisors")
					continue
				}

				operationsHypers, err := o.operationsCli.ListHypervisors(ctx, &operationsv1.ListHypervisorsRequest{})
				if err != nil {
					o.log.Error().Err(err).Msg("list the hypervisors of the operations service")
					continue
				}

				o.log.Debug().Array("isard_hypervisors", log.NewModelHypervisors(hypers)).Array("infrastructure_hypervisors", log.NewOperationsV1ListHypervisorsResponse(operationsHypers)).Msg("infrastructure state")

				// Cleanup "zombie" hypervisors (hypervisors that no longer exist in the operations service, but are still in the API but are not online)
				if err := o.cleanup(ctx, hypers, operationsHypers.GetHypervisors()); err != nil {
					o.log.Error().Err(err).Msg("cleanup zombie hypervisors")
				}

				scale, err := o.director.NeedToScaleHypervisors(ctx, operationsHypers.Hypervisors, hypers)
				if err != nil {
					o.log.Error().Err(err).Msg("check if there are hypervisors that need to scale")
					continue
				}

				timeout, cancel := context.WithTimeout(ctx, o.operationsTimeout)
				defer cancel()

				if len(scale.HypersToRemoveFromDeadRow) != 0 {
					if o.dryRun {
						o.log.Info().Bool("DRY_RUN", true).Array("ids", log.NewModelStrArray(scale.HypersToRemoveFromDeadRow)).Msg("cancel hypervisors destruction")

					} else {
						go o.removeHypervisorsFromDeadRow(timeout, scale.HypersToRemoveFromDeadRow)
					}
				}

				if len(scale.HypersToRemoveFromOnlyForced) != 0 {
					if o.dryRun {
						o.log.Info().Bool("DRY_RUN", true).Array("ids", log.NewModelStrArray(scale.HypersToRemoveFromOnlyForced)).Msg("unlimit hypervisors")

					} else {
						go o.removeHypervisorsFromOnlyForced(timeout, scale.HypersToRemoveFromOnlyForced)
					}
				}

				if scale.Create != nil {
					if o.dryRun {
						o.log.Info().Bool("DRY_RUN", true).Array("ids", log.NewModelStrArray(scale.Create.Ids)).Msg("create hypervisor")

					} else {
						go o.createHypervisors(timeout, scale.Create)
					}
				}

				if len(scale.HypersToAddToDeadRow) != 0 {
					if o.dryRun {
						o.log.Info().Bool("DRY_RUN", true).Array("ids", log.NewModelStrArray(scale.HypersToAddToDeadRow)).Msg("set hypervisors to destroy")

					} else {
						go o.addHypervisorsToDeadRow(timeout, scale.HypersToAddToDeadRow)
					}
				}

				if scale.Destroy != nil {
					if o.dryRun {
						o.log.Info().Bool("DRY_RUN", true).Array("ids", log.NewModelStrArray(scale.Destroy.Ids)).Msg("destroy hypervisors")

					} else {
						go o.destroyHypervisors(timeout, scale.Destroy)
					}
				}
			}
		}
	}
}
