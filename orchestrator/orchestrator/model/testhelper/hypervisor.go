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
		h.OrchestratorHypervisor.OnlyForced = apiv4.NewOptBool(v)
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
		h.OrchestratorHypervisor.MinFreeMemGB = apiv4.NewOptInt(v)
	}
}

func WithDesktopsStarted(v int) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.DesktopsStarted = apiv4.NewOptInt(v)
	}
}

func WithGpuOnly(v bool) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.GpuOnly = apiv4.NewOptBool(v)
	}
}

func WithBuffering(v bool) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.BufferingHyper = apiv4.NewOptBool(v)
	}
}

func WithOrchestratorManaged(v bool) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.OrchestratorManaged = apiv4.NewOptBool(v)
	}
}

// WithDestroyTime sets the DestroyTime field as an RFC3339Nano string.
// A zero time sets the field to unset.
func WithDestroyTime(t time.Time) HyperOption {
	return func(h *model.Hypervisor) {
		if t.IsZero() {
			h.OrchestratorHypervisor.DestroyTime = apiv4.OptString{}
		} else {
			h.OrchestratorHypervisor.DestroyTime = apiv4.NewOptString(t.Format(time.RFC3339Nano))
		}
	}
}

// WithBookingsEndTime sets the BookingsEndTime field as an RFC3339Nano string.
// A zero time sets the field to unset.
func WithBookingsEndTime(t time.Time) HyperOption {
	return func(h *model.Hypervisor) {
		if t.IsZero() {
			h.OrchestratorHypervisor.BookingsEndTime = apiv4.OptString{}
		} else {
			h.OrchestratorHypervisor.BookingsEndTime = apiv4.NewOptString(t.Format(time.RFC3339Nano))
		}
	}
}

func WithGPUs(gpus []apiv4.OrchestratorHypervisorGPU) HyperOption {
	return func(h *model.Hypervisor) {
		h.OrchestratorHypervisor.Gpus = gpus
	}
}
