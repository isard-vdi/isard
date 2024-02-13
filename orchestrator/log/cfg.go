package log

import (
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi/orchestrator/cfg"
)

type ModelCfg struct {
	cfg cfg.DirectorRata
}

func NewModelCfg(cfg cfg.DirectorRata) ModelCfg {
	return ModelCfg{cfg}
}

func (m ModelCfg) MarshalZerologObject(e *zerolog.Event) {
	e.Int("min_cpu", m.cfg.MinCPU).
		Int("min_ram", m.cfg.MinRAM).
		Any("min_cpu_hourly", m.cfg.MinCPUHourly).
		Any("min_ram_hourly", m.cfg.MinRAMHourly).
		Int("min_ram_limit_percent", m.cfg.MinRAMLimitPercent).
		Int("min_ram_limit_margin", m.cfg.MinRAMLimitMargin).
		Any("min_ram_limit_margin_hourly", m.cfg.MinRAMLimitMarginHourly).
		Int("max_cpu", m.cfg.MaxCPU).
		Int("max_ram", m.cfg.MaxRAM).
		Any("max_cpu_hourly", m.cfg.MaxCPUHourly).
		Any("max_ram_hourly", m.cfg.MaxRAMHourly).
		Int("max_ram_limit_percent", m.cfg.MaxRAMLimitPercent).
		Int("max_ram_limit_margin", m.cfg.MaxRAMLimitMargin).
		Any("max_ram_limit_margin_hourly", m.cfg.MaxRAMLimitMarginHourly).
		Int("hyper_min_cpu", m.cfg.HyperMinCPU).
		Int("hyper_min_ram", m.cfg.HyperMinRAM).
		Int("hyper_max_cpu", m.cfg.HyperMaxCPU).
		Int("hyper_max_ram", m.cfg.HyperMaxRAM)
}
