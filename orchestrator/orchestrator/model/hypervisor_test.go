package model_test

import (
	"testing"

	"github.com/stretchr/testify/assert"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"

	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/model"
)

func TestHypervisorLoadsRAMFromStats(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	raw := &apiv4.OrchestratorHypervisor{
		ID:     "hyp-1",
		Status: model.HypervisorStatusOnline,
		Stats: apiv4.NewOptOrchestratorHypervisorStats(apiv4.OrchestratorHypervisorStats{
			MemStats: apiv4.OrchestratorHypervisorStatsMem{
				Total: 4 * 1024 * 1024, // 4 GB in KB
				Used:  1 * 1024 * 1024, // 1 GB in KB
			},
		}),
	}

	h := model.NewHypervisor(raw)

	assert.Equal(model.ResourceLoad{Total: 4096, Used: 1024, Free: 3072}, h.RAM)
}

func TestHypervisorLoadsCPUFromStats(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	raw := &apiv4.OrchestratorHypervisor{
		ID:     "hyp-2",
		Status: model.HypervisorStatusOnline,
		Stats: apiv4.NewOptOrchestratorHypervisorStats(apiv4.OrchestratorHypervisorStats{
			CPU5min: apiv4.OrchestratorHypervisorStatsCPU{
				Used: 42.5,
				Idle: 57.5,
			},
		}),
	}

	h := model.NewHypervisor(raw)

	assert.Equal(model.ResourceLoad{Total: 100, Used: 43, Free: 57}, h.CPU)
}

func TestHypervisorNoStats(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	raw := &apiv4.OrchestratorHypervisor{
		ID:     "hyp-3",
		Status: model.HypervisorStatusOffline,
	}

	h := model.NewHypervisor(raw)

	assert.Equal(model.ResourceLoad{}, h.CPU)
	assert.Equal(model.ResourceLoad{}, h.RAM)
}

func TestHypervisorRAMFreeUsesByteDivision(t *testing.T) {
	t.Parallel()

	raw := &apiv4.OrchestratorHypervisor{
		ID:     "hyp-byte-diff",
		Status: model.HypervisorStatusOnline,
		Stats: apiv4.NewOptOrchestratorHypervisorStats(apiv4.OrchestratorHypervisorStats{
			MemStats: apiv4.OrchestratorHypervisorStatsMem{
				Total: 8388608,
				Used:  8388607,
			},
		}),
	}

	h := model.NewHypervisor(raw)

	// Without fix: Total/1024 - Used/1024 = 8192-8191 = 1 (wrong).
	// With fix: (Total-Used)/1024 = 1/1024 = 0 (correct).
	assert.New(t).Equal(0, h.RAM.Free)
}
