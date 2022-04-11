package collector

import (
	"context"
	"fmt"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/stats/cfg"

	"github.com/influxdata/influxdb-client-go/v2/api/write"
	"libvirt.org/go/libvirt"
)

type Hypervisor struct {
	hyp  string
	mux  *sync.Mutex
	conn *libvirt.Connect
}

func NewHypervisor(mux *sync.Mutex, cfg cfg.Cfg, conn *libvirt.Connect) *Hypervisor {
	return &Hypervisor{
		hyp:  cfg.Domain,
		mux:  mux,
		conn: conn,
	}
}

func (h *Hypervisor) String() string {
	return "hypervisor"
}

func (h *Hypervisor) Close() error {
	return nil
}

func (h *Hypervisor) Collect(ctx context.Context) ([]*write.Point, error) {
	start := time.Now()

	cpu, err := h.collectCPU()
	if err != nil {
		return nil, err
	}

	mem, err := h.collectMemory()
	if err != nil {
		return nil, err
	}

	return transformLibvirtData(start, h.String(), map[string]string{
		"hypervisor": h.hyp,
	}, "", map[string]interface{}{
		"cpu":    cpu,
		"cpuSet": true,
		"mem":    mem,
		"memSet": true,
	})
}

func (h *Hypervisor) collectCPU() (*libvirt.NodeCPUStats, error) {
	h.mux.Lock()
	defer h.mux.Unlock()

	cpu, err := h.conn.GetCPUStats(int(libvirt.NODE_CPU_STATS_ALL_CPUS), 0)
	if err != nil {
		return nil, fmt.Errorf("collect cpu stats: %w", err)
	}

	return cpu, nil
}

func (h *Hypervisor) collectMemory() (*libvirt.NodeMemoryStats, error) {
	h.mux.Lock()
	defer h.mux.Unlock()

	mem, err := h.conn.GetMemoryStats(libvirt.NODE_MEMORY_STATS_ALL_CELLS, 0)
	if err != nil {
		return nil, fmt.Errorf("collect memory stats: %w", err)
	}

	return mem, nil
}
