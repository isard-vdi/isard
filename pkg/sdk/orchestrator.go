package isardvdi

import (
	"context"
	"fmt"
	"math"
	"net/http"
	"time"
)

type OrchestratorHypervisor struct {
	ID                  string                      `json:"id,omitempty"`
	Status              HypervisorStatus            `json:"status,omitempty"`
	OnlyForced          bool                        `json:"only_forced,omitempty"`
	Buffering           bool                        `json:"buffering_hyper,omitempty"`
	DestroyTime         time.Time                   `json:"destroy_time,omitempty"`
	Stats               OrchestratorHypervisorStats `json:"stats,omitempty"`
	MinFreeMemGB        int                         `json:"min_free_mem_gb,omitempty"`
	OrchestratorManaged bool                        `json:"orchestrator_managed,omitempty"`
	DesktopsStarted     int                         `json:"desktops_started,omitempty"`
	CPU                 OrchestratorResourceLoad    `json:"-"`
	RAM                 OrchestratorResourceLoad    `json:"-"`
}

func (o *OrchestratorHypervisor) calcLoad() {
	o.CPU = OrchestratorResourceLoad{
		Total: 100,
		Used:  int(math.Ceil(float64(o.Stats.CPU5Min.Used))),
		Free:  int(math.Floor(float64(o.Stats.CPU5Min.Idle))),
	}

	o.RAM = OrchestratorResourceLoad{
		Total: o.Stats.Mem.Total / 1024,
		Used:  (o.Stats.Mem.Total - o.Stats.Mem.Available) / 1024,
		Free:  o.Stats.Mem.Available / 1024,
	}
}

type OrchestratorHypervisorStats struct {
	CPUCurrent OrchestratorHypervisorStatsCPU `json:"cpu_current,omitempty"`
	CPU5Min    OrchestratorHypervisorStatsCPU `json:"cpu_5min,omitempty"`
	Mem        OrchestratorHypervisorStatsMem `json:"mem_stats,omitempty"`
}

type OrchestratorHypervisorStatsMem struct {
	Available int `json:"available,omitempty"`
	Buffers   int `json:"buffers,omitempty"`
	Cached    int `json:"cached,omitempty"`
	Free      int `json:"free,omitempty"`
	Total     int `json:"total,omitempty"`
}

type OrchestratorHypervisorStatsCPU struct {
	Idle   float32 `json:"idle,omitempty"`
	Iowait float32 `json:"iowait,omitempty"`
	Kernel float32 `json:"kernel,omitempty"`
	Used   float32 `json:"used,omitempty"`
	User   float32 `json:"user,omitempty"`
}

type OrchestratorResourceLoad struct {
	Total int
	Used  int
	Free  int
}

func (c *Client) OrchestratorHypervisorList(ctx context.Context) ([]*OrchestratorHypervisor, error) {
	req, err := c.newRequest(http.MethodGet, "orchestrator/hypervisors", nil)
	if err != nil {
		return nil, err
	}

	hypervisors := []*OrchestratorHypervisor{}
	if _, err := c.do(ctx, req, &hypervisors); err != nil {
		return nil, fmt.Errorf("orchestrator hypervisor list: %w", err)
	}

	for _, h := range hypervisors {
		h.calcLoad()
	}

	return hypervisors, nil
}

func (c *Client) OrchestratorHypervisorGet(ctx context.Context, id string) (*OrchestratorHypervisor, error) {
	req, err := c.newRequest(http.MethodGet, fmt.Sprintf("orchestrator/hypervisor/%s", id), nil)
	if err != nil {
		return nil, err
	}

	hypervisor := &OrchestratorHypervisor{}
	if _, err := c.do(ctx, req, hypervisor); err != nil {
		return nil, fmt.Errorf("orchestrator hypervisor list: %w", err)
	}

	hypervisor.calcLoad()

	return hypervisor, nil
}

func (c *Client) OrchestratorHypervisorManage(ctx context.Context, id string) error {
	req, err := c.newRequest(http.MethodPost, fmt.Sprintf("orchestrator/hypervisor/%s/manage", id), nil)
	if err != nil {
		return err
	}

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("manage hypervisor: %w", err)
	}

	return nil
}

func (c *Client) OrchestratorHypervisorUnmanage(ctx context.Context, id string) error {
	req, err := c.newRequest(http.MethodDelete, fmt.Sprintf("orchestrator/hypervisor/%s/manage", id), nil)
	if err != nil {
		return err
	}

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("unmanage hypervisor: %w", err)
	}

	return nil
}

func (c *Client) OrchestratorHypervisorAddToDeadRow(ctx context.Context, id string) (time.Time, error) {
	req, err := c.newRequest(http.MethodPost, fmt.Sprintf("orchestrator/hypervisor/%s/dead_row", id), nil)
	if err != nil {
		return time.Time{}, err
	}

	rsp := struct {
		DestroyTime *time.Time `json:"destroy_time,omitempty"`
	}{}
	if _, err := c.do(ctx, req, &rsp); err != nil {
		return time.Time{}, fmt.Errorf("add hypervisor to the dead row: %w", err)
	}

	return *rsp.DestroyTime, nil
}

func (c *Client) OrchestratorHypervisorRemoveFromDeadRow(ctx context.Context, id string) error {
	req, err := c.newRequest(http.MethodDelete, fmt.Sprintf("orchestrator/hypervisor/%s/dead_row", id), nil)
	if err != nil {
		return err
	}

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("remove hypervisor to the dead row: %w", err)
	}

	return nil
}

func (c *Client) OrchestratorHypervisorStopDesktops(ctx context.Context, id string) error {
	req, err := c.newRequest(http.MethodDelete, fmt.Sprintf("orchestrator/hypervisor/%s/desktops", id), nil)
	if err != nil {
		return err
	}

	if _, err := c.do(ctx, req, nil); err != nil {
		return fmt.Errorf("stop hypervisor desktops: %w", err)
	}

	return nil
}
