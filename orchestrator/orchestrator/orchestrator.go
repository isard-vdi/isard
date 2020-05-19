package orchestrator

import (
	"sync"
	"time"

	"go.uber.org/zap"

	"github.com/rs/xid"
)

type Interface interface {
	AddHyper(host string, healthcheck time.Time)
	RemoveHyper(host string)
	SetHyperMigrating(host string)
}

type hyperState int

const (
	hyperStateUnknown hyperState = iota
	hyperStateOK
	hyperStateMigrating
)

type hyper struct {
	id          xid.ID
	state       hyperState
	healthcheck time.Time
}

type Orchestrator struct {
	mux    sync.Mutex
	sugar  *zap.SugaredLogger
	hypers map[string]hyper
}

func New(sugar *zap.SugaredLogger) *Orchestrator {
	return &Orchestrator{
		sugar:  sugar,
		hypers: map[string]hyper{},
	}
}

func (o *Orchestrator) AddHyper(host string, healthcheck time.Time) {
	o.mux.Lock()
	defer o.mux.Unlock()

	if h, ok := o.hypers[host]; ok {
		h.healthcheck = healthcheck
		return
	}

	o.hypers[host] = hyper{
		id:          xid.New(),
		state:       hyperStateOK,
		healthcheck: healthcheck,
	}

	o.sugar.Infow("added hypervisor to the pool",
		"host", host,
	)
}

func (o *Orchestrator) RemoveHyper(host string) {
	o.mux.Lock()
	defer o.mux.Unlock()

	if _, ok := o.hypers[host]; ok {
		delete(o.hypers, host)
	}
}

func (o *Orchestrator) SetHyperMigrating(host string) {
	o.mux.Lock()
	defer o.mux.Unlock()

	if _, ok := o.hypers[host]; ok {
		h := o.hypers[host]
		h.state = hyperStateMigrating
		o.hypers[host] = h
	}
}
