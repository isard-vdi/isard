package collector

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/stats/cfg"

	"github.com/influxdata/influxdb-client-go/v2/api/write"
	"libvirt.org/go/libvirt"
)

type Hypervisor struct {
	wg     *sync.WaitGroup
	domain string
	conn   *libvirt.Connect
}

func NewHypervisor(wg *sync.WaitGroup, cfg cfg.Cfg) (*Hypervisor, error) {
	conn, err := libvirt.NewConnectReadOnly(cfg.Collectors.Hypervisor.LibvirtURI)
	if err != nil {
		return nil, fmt.Errorf("connect to libvirt: %w", err)
	}

	alive, err := conn.IsAlive()
	if err != nil || !alive {
		return nil, errors.New("connection not alive")
	}

	return &Hypervisor{
		wg:     wg,
		domain: cfg.Domain,
		conn:   conn,
	}, nil
}

func (h *Hypervisor) String() string {
	return "hypervisor"
}

func (h *Hypervisor) Close() error {
	_, err := h.conn.Close()

	h.wg.Done()
	return err
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

	doms, err := h.collectDomains()
	if err != nil {
		return nil, err
	}

	return []*write.Point{write.NewPoint(
		h.String(),
		map[string]string{
			"hypervisor": h.domain,
		},
		mergeMaps(cpu, mem, doms),
		start,
	)}, nil
}

func (h *Hypervisor) collectCPU() (map[string]interface{}, error) {
	cpu, err := h.conn.GetCPUStats(int(libvirt.NODE_CPU_STATS_ALL_CPUS), 0)
	if err != nil {
		return nil, fmt.Errorf("collect cpu stats: %w", err)
	}

	data, err := transformLibvirtData("cpu", cpu)
	if err != nil {
		return nil, fmt.Errorf("transform cpu stats: %w", err)
	}

	return data, nil
}

func (h *Hypervisor) collectMemory() (map[string]interface{}, error) {
	mem, err := h.conn.GetMemoryStats(libvirt.NODE_MEMORY_STATS_ALL_CELLS, 0)
	if err != nil {
		return nil, fmt.Errorf("collect memory stats: %w", err)
	}

	data, err := transformLibvirtData("mem", mem)
	if err != nil {
		return nil, fmt.Errorf("transform memory stats: %w", err)
	}

	return data, nil
}

func (h *Hypervisor) collectDomains() (map[string]interface{}, error) {
	// doms, err := h.conn.ListAllDomains(libvirt.CONNECT_LIST_DOMAINS_RUNNING)
	// if err != nil {
	// 	return nil, fmt.Errorf("collect domains stats: %w", err)
	// }

	return map[string]interface{}{"total_domains": "NOT IMPLEMENTED"}, nil
}
