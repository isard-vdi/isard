package orchestrator

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-cli/pkg/client"
	"gitlab.com/isard/isardvdi/orchestrator/model"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var ErrTimeout = errors.New("operation timeout")

type Orchestrator struct {
	director director.Director

	pollingInterval   time.Duration
	operationsTimeout time.Duration

	db            r.QueryExecutor
	operationsCli operationsv1.OperationsServiceClient
	apiSecret     string
	apiCli        client.Interface

	scaleMux sync.Mutex
	scaling  bool

	log *zerolog.Logger
	wg  *sync.WaitGroup
}

type NewOrchestratorOpts struct {
	Log *zerolog.Logger
	WG  *sync.WaitGroup

	PollingInterval   time.Duration
	OperationsTimeout time.Duration

	DB            r.QueryExecutor
	Director      director.Director
	OperationsCli operationsv1.OperationsServiceClient

	APISecret string
	APICli    client.Interface
}

func New(cfg *NewOrchestratorOpts) *Orchestrator {
	log2 := cfg.Log.With().Str("director", cfg.Director.String()).Logger()

	return &Orchestrator{
		director: cfg.Director,

		pollingInterval:   cfg.PollingInterval,
		operationsTimeout: cfg.OperationsTimeout,

		db:            cfg.DB,
		operationsCli: cfg.OperationsCli,
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
			hypers, err := model.GetHypervisors(ctx, o.db)
			if err != nil {
				o.log.Error().Err(err).Msg("get hypervisors")
				continue
			}

			if !o.scaling {
				create, destroy, err := o.director.NeedToScaleHypervisors(ctx, hypers)
				if err != nil {
					o.log.Error().Err(err).Msg("check if there are hypervisors that need to scale")
					continue
				}

				timeout, cancel := context.WithTimeout(ctx, o.operationsTimeout)
				defer cancel()

				if create != nil {
					go o.createHypervisor(timeout, create)
				}

				if destroy != nil {
					go o.destroyHypervisor(timeout, destroy)
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
