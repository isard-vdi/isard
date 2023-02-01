package model

import (
	"context"
	"errors"
	"fmt"
	"math"
	"time"

	"gitlab.com/isard/isardvdi-cli/pkg/client"
	"gitlab.com/isard/isardvdi/pkg/db"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Hypervisor struct {
	ID          string                  `rethinkdb:"id"`
	Status      client.HypervisorStatus `rethinkdb:"status"`
	OnlyForced  bool                    `rethinkdb:"only_forced"`
	Buffering   bool                    `rethinkdb:"buffering_hyper"`
	DestroyTime time.Time               `rethinkdb:"destroy_time"`
	Stats       HypervisorStats         `rethinkdb:"stats"`
	CPU         ResourceLoad            `rethinkdb:"-"`
	RAM         ResourceLoad            `rethinkdb:"-"`
}

type HypervisorStats struct {
	CPUCurrent HypervisorStatsCPU `rethinkdb:"cpu_current"`
	CPU5Min    HypervisorStatsCPU `rethinkdb:"cpu_5min"`
	Mem        HypervisorStatsMem `rethinkdb:"mem_stats"`
}

type HypervisorStatsMem struct {
	Available int `rethinkdb:"available"`
	Buffers   int `rehthinkdb:"buffers"`
	Cached    int `rethinkdb:"cached"`
	Free      int `rethinkdb:"free"`
	Total     int `rethinkdb:"total"`
}

type HypervisorStatsCPU struct {
	Idle   float32 `rethinkdb:"idle"`
	Iowait float32 `rethinkdb:"iowait"`
	Kernel float32 `rethinkdb:"kernel"`
	Used   float32 `rethinkdb:"used"`
	User   float32 `rethinkdb:"user"`
}

type ResourceLoad struct {
	Total int
	Used  int
	Free  int
}

func (h *Hypervisor) Load(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("hypervisors").Get(h.ID).Run(sess)
	if err != nil {
		return err
	}
	defer res.Close()

	if err := res.One(h); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return db.ErrNotFound
		}

		return fmt.Errorf("read db response: %w", err)
	}

	calcLoad(h)

	return nil
}

func GetHypervisors(ctx context.Context, sess r.QueryExecutor) ([]*Hypervisor, error) {
	// Get Hypervisors
	res, err := r.Table("hypervisors").Run(sess)
	if err != nil {
		return nil, fmt.Errorf("get all hypervisors: %w", err)
	}

	h := []*Hypervisor{}
	if err := res.All(&h); err != nil {
		return nil, fmt.Errorf("read DB response when listing all hypervisors: %w", err)
	}
	res.Close()

	for _, hyper := range h {
		calcLoad(hyper)
	}

	return h, nil
}

func calcLoad(h *Hypervisor) {
	h.CPU = ResourceLoad{
		Total: 100,
		Used:  int(math.Ceil(float64(h.Stats.CPU5Min.Used))),
		Free:  int(math.Floor(float64(h.Stats.CPU5Min.Idle))),
	}
	h.RAM = ResourceLoad{
		Total: h.Stats.Mem.Total / 1024,
		Used:  (h.Stats.Mem.Total - h.Stats.Mem.Available) / 1024,
		Free:  h.Stats.Mem.Available / 1024,
	}
}

func (h *Hypervisor) AddToDeadRow(destroy time.Time, sess r.QueryExecutor) error {
	h.DestroyTime = destroy
	h.OnlyForced = true

	_, err := r.Table("hypervisors").Get(h.ID).Update(map[string]interface{}{"destroy_time": destroy, "only_forced": true}).Run(sess)
	return err
}

func (h *Hypervisor) RemoveFromDeadRow(sess r.QueryExecutor) error {
	_, err := r.Table("hypervisors").Get(h.ID).Update(map[string]interface{}{"destroy_time": nil}).Run(sess)
	return err
}
