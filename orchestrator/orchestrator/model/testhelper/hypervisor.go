package testhelper

import (
	"time"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"

	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/model"
)

type HyperOption func(*model.Hypervisor)

func Hypervisor(opts ...HyperOption) *model.Hypervisor {
	h := model.NewHypervisor(&apiv4.OrchestratorHypervisor{
		ID:     "test-hyper",
		Status: model.HypervisorStatusOnline,
		Stats:  apiv4.NilOrchestratorHypervisorStats{Null: true},
	})
	for _, opt := range opts {
		opt(h)
	}
	return h
}

func WithID(id string) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.ID = id
	}
}

func WithStatus(status string) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.Status = status
	}
}

func WithOnlyForced(v bool) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.OnlyForced = v
	}
}

// WithRAM sets the RAM ResourceLoad directly (bypassing Stats).
func WithRAM(total, used, free int) HyperOption {
	return func(h *model.Hypervisor) {
		h.RAM = model.ResourceLoad{Total: total, Used: used, Free: free}
	}
}

// WithCPU sets the CPU ResourceLoad directly (bypassing Stats).
func WithCPU(total, used, free int) HyperOption {
	return func(h *model.Hypervisor) {
		h.CPU = model.ResourceLoad{Total: total, Used: used, Free: free}
	}
}

func WithMinFreeMemGB(v int) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.MinFreeMemGB = v
	}
}

func WithDesktopsStarted(v int) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.DesktopsStarted = v
	}
}

func WithGpuOnly(v bool) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.GpuOnly = v
	}
}

func WithBuffering(v bool) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.BufferingHyper = v
	}
}

func WithOrchestratorManaged(v bool) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.OrchestratorManaged = v
	}
}

// WithDestroyTime sets the DestroyTime field.
// A zero time sets the field to unset.
func WithDestroyTime(t time.Time) HyperOption {
	return func(h *model.Hypervisor) {
		if t.IsZero() {
			h.OrchestratorHypervisor.DestroyTime = apiv4.NilDateTime{Null: true}
		} else {
			h.OrchestratorHypervisor.DestroyTime = apiv4.NewNilDateTime(t)
		}
	}
}

// WithBookingsEndTime sets the BookingsEndTime field.
// A zero time sets the field to unset.
func WithBookingsEndTime(t time.Time) HyperOption {
	return func(h *model.Hypervisor) {
		if t.IsZero() {
			h.OrchestratorHypervisor.BookingsEndTime = apiv4.NilDateTime{Null: true}
		} else {
			h.OrchestratorHypervisor.BookingsEndTime = apiv4.NewNilDateTime(t)
		}
	}
}

func WithGPUs(gpus []apiv4.OrchestratorHypervisorGPU) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.Gpus = gpus
	}
}
