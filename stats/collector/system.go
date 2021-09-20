package collector

import (
	"context"
	"fmt"
	"time"

	"gitlab.com/isard/isardvdi/stats/cfg"

	"github.com/influxdata/influxdb-client-go/v2/api/write"
	"github.com/shirou/gopsutil/v3/cpu"
)

type System struct {
	domain string
}

func NewSystem(cfg cfg.Cfg) *System {
	return &System{domain: cfg.Domain}
}

func (s *System) String() string {
	return "system"
}

func (s *System) Close() error {
	return nil
}

func (s *System) Collect(ctx context.Context) (*write.Point, error) {
	start := time.Now()

	cpu, err := s.collectCPU()
	if err != nil {
		return nil, err
	}

	return write.NewPoint(
		s.String(),
		map[string]string{
			"hypervisor": s.domain,
		},
		mergeMaps(cpu),
		start,
	), nil
}

func (s *System) collectCPU() (map[string]interface{}, error) {
	info, err := cpu.Info()
	if err != nil {
		return nil, fmt.Errorf("collect cpu stats: %w", err)
	}

	usage, err := cpu.Percent(5*time.Second, false)
	if err != nil {
		return nil, fmt.Errorf("collect cpu usage: %w", err)
	}

	return map[string]interface{}{
		"cpu_cores":     info[0].Cores,
		"cpu_threads":   len(info),
		"cpu_frequency": info[0].Mhz,
		"cpu_usage":     usage[0],
	}, nil
}
