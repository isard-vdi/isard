package model

import (
	"math"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
)

const (
	HypervisorStatusOnline  = "Online"
	HypervisorStatusOffline = "Offline"
	HypervisorStatusError   = "Error"
)

type ResourceLoad struct {
	Total int
	Used  int
	Free  int
}

type Hypervisor struct {
	*apiv4.OrchestratorHypervisor

	CPU ResourceLoad
	RAM ResourceLoad
}

func NewHypervisor(raw *apiv4.OrchestratorHypervisor) *Hypervisor {
	h := &Hypervisor{OrchestratorHypervisor: raw}
	h.calcLoad()
	return h
}

func NewHypervisors(raw []apiv4.OrchestratorHypervisor) []*Hypervisor {
	result := make([]*Hypervisor, len(raw))
	for i := range raw {
		result[i] = NewHypervisor(&raw[i])
	}
	return result
}

func (h *Hypervisor) calcLoad() {
	stats, ok := h.OrchestratorHypervisor.Stats.Get()
	if !ok {
		return
	}

	cpu := stats.CPU5min
	h.CPU = ResourceLoad{
		Total: 100,
		Used:  int(math.Ceil(cpu.Used)),
		Free:  int(math.Floor(cpu.Idle)),
	}

	mem := stats.MemStats
	h.RAM = ResourceLoad{
		Total: mem.Total / 1024,
		Used:  mem.Used / 1024,
		Free:  (mem.Total - mem.Used) / 1024,
	}
}
