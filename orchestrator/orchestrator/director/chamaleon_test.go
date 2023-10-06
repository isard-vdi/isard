package director_test

import (
	"context"
	"os"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi-sdk-go"
	apiMock "gitlab.com/isard/isardvdi-sdk-go/mock"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

func TestChamaleonNeedToScaleHypervisors(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		AvailHypers               []*operationsv1.ListHypervisorsResponseHypervisor
		Hypers                    []*isardvdi.OrchestratorHypervisor
		PrepareAPI                func(*apiMock.Client)
		ExpectedErr               string
		ExpectedRemoveDeadRow     []string
		ExpectedCreateHypervisor  *operationsv1.CreateHypervisorsRequest
		ExpectedAddDeadRow        []string
		ExpectedDestroyHypervisor *operationsv1.DestroyHypervisorsRequest
	}{
		"if there are enough units, it should return 0": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				Status:     isardvdi.HypervisorStatusOnline,
				OnlyForced: false,
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}},
			PrepareAPI: func(api *apiMock.Client) {
				api.On("OrchestratorGPUBookingList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.OrchestratorGPUBooking{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now(),
						Units: 5,
					},
					Create: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(30 * time.Minute),
						Units: 7,
					},
					Destroy: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(60 * time.Minute),
						Units: 4,
					},
				}}, nil)
			},
		},
		"if there are not enough units, it should return the ID of the hypervisor that needs to be created": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:           "testing little",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}, {
				Id:           "testing good",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}, {
				Id:           "testing GIGANTIC",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}, {
				Id:    "existing",
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
			}},
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:         "existing",
				Status:     isardvdi.HypervisorStatusOnline,
				OnlyForced: false,
			}},
			PrepareAPI: func(api *apiMock.Client) {
				api.On("OrchestratorGPUBookingList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.OrchestratorGPUBooking{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now(),
						Units: 5,
					},
					Create: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(30 * time.Minute),
						Units: 7,
					},
					Destroy: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(60 * time.Minute),
						Units: 4,
					},
				}}, nil)
			},
			ExpectedCreateHypervisor: &operationsv1.CreateHypervisorsRequest{
				Ids: []string{"testing good"},
			},
		},
		"if there are not enough units, it should return the IDs of multiple hypervisors if required that need to be created": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:           "testing good 1",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}, {
				Id:           "testing NOT A10",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "AMD",
					Model: "A10",
				}},
			}, {
				Id:           "testing GIGANTIC",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}, {
				Id:           "testing good 2",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}, {
				Id:    "existing",
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
			}},
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:         "existing",
				Status:     isardvdi.HypervisorStatusOnline,
				OnlyForced: false,
			}},
			PrepareAPI: func(api *apiMock.Client) {
				api.On("OrchestratorGPUBookingList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.OrchestratorGPUBooking{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now(),
						Units: 8, // One A10 card has 6 4Q profiles
					},
					Create: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(30 * time.Minute),
						Units: 9,
					},
					Destroy: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(60 * time.Minute),
						Units: 4,
					},
				}}, nil)
			},
			ExpectedCreateHypervisor: &operationsv1.CreateHypervisorsRequest{
				Ids: []string{"testing good 1", "testing good 2"},
			},
		},
		"if there's not too much free units, it should add the biggest hypervisor to the dead row": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:                  "to keep",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  5,
				}},
			}, {
				ID:                  "AMONGUS!",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
				}, {
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
				}, {
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
				}, {
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
				}},
			}},
			PrepareAPI: func(api *apiMock.Client) {
				api.On("OrchestratorGPUBookingList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.OrchestratorGPUBooking{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now(),
						Units: 4, // One A10 card has 6 4Q profiles
					},
					Create: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(30 * time.Minute),
						Units: 4,
					},
					Destroy: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(60 * time.Minute),
						Units: 4,
					},
				}}, nil)
			},
			ExpectedAddDeadRow: []string{"AMONGUS!"},
		},
		"if there's not enough units, but there are hypervisors on the dead row, if should remove those from it": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:                  "destroy 1",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          true,
				OrchestratorManaged: true,
				DestroyTime:         time.Now().Add(-1 * time.Hour),
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}, {
				ID:                  "destroy 2",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          true,
				OrchestratorManaged: true,
				DestroyTime:         time.Now().Add(1 * time.Hour),
				DesktopsStarted:     0,
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}, {
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}},
			PrepareAPI: func(api *apiMock.Client) {
				api.On("OrchestratorGPUBookingList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.OrchestratorGPUBooking{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now(),
						Units: 13,
					},
					Create: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(30 * time.Minute),
						Units: 7,
					},
					Destroy: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(60 * time.Minute),
						Units: 8,
					},
				}}, nil)
			},
			ExpectedRemoveDeadRow: []string{"destroy 1", "destroy 2"},
		},
		"if there's an hypervisor that's been too much time on the dead row, KILL THEM!!! >:(": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:                  "destroy 1",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}, {
				ID:                  "destroy 2",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          true,
				OrchestratorManaged: true,
				DestroyTime:         time.Now().Add(1 * time.Hour),
				DesktopsStarted:     0,
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}, {
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}},
			PrepareAPI: func(api *apiMock.Client) {
				api.On("OrchestratorGPUBookingList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.OrchestratorGPUBooking{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now(),
						Units: 4,
					},
					Create: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(30 * time.Minute),
						Units: 3,
					},
					Destroy: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(60 * time.Minute),
						Units: 5,
					},
				}}, nil)
			},
			ExpectedDestroyHypervisor: &operationsv1.DestroyHypervisorsRequest{
				Ids: []string{"destroy 2"},
			},
		},
		"if there are multiple hypervisor that have been too much time on the dead row, have 0 desktops started or have exceeded the booking time, KILL THEM!!! >:(": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:                  "destroy 1",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				DestroyTime:         time.Now().Add(-1 * time.Hour),
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}, {
				ID:                  "non managed",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: false,
				DestroyTime:         time.Now().Add(-1 * time.Hour),
				DesktopsStarted:     234,
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}, {
				ID:                  "destroy 2",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				DestroyTime:         time.Now().Add(1 * time.Hour),
				DesktopsStarted:     0,
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}, {
				ID:                  "destroy 3",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				DestroyTime:         time.Now().Add(1 * time.Hour),
				DesktopsStarted:     23,
				BookingsEndTime:     time.Now().Add(-1 * time.Hour),
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}},
			PrepareAPI: func(api *apiMock.Client) {
				api.On("OrchestratorGPUBookingList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.OrchestratorGPUBooking{}, nil)
			},
			ExpectedDestroyHypervisor: &operationsv1.DestroyHypervisorsRequest{
				Ids: []string{"destroy 1", "destroy 2", "destroy 3"},
			},
		},
		"if the available hypervisors are not enough, it should still create the maximum hypervisors": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:           "NOT BIG HUMONGUS AMONGUS",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}, {
				Id:           "unavailable hypervisor",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}},
			Hypers: []*isardvdi.OrchestratorHypervisor{{}},
			PrepareAPI: func(api *apiMock.Client) {
				api.On("OrchestratorGPUBookingList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.OrchestratorGPUBooking{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "24Q",
					Now: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now(),
						Units: 2,
					},
					Create: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(30 * time.Minute),
						Units: 0,
					},
				}}, nil)
			},
			ExpectedCreateHypervisor: &operationsv1.CreateHypervisorsRequest{
				Ids: []string{"NOT BIG HUMONGUS AMONGUS"},
			},
		},
		"if there are no suitable hypervisors for scaling up, return an error": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:           "NOT BIG HUMONGUS AMONGUS",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "T4",
				}},
			}, {
				Id:           "unavailable hypervisor",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}},
			Hypers: []*isardvdi.OrchestratorHypervisor{{}},
			PrepareAPI: func(api *apiMock.Client) {
				api.On("OrchestratorGPUBookingList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.OrchestratorGPUBooking{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "24Q",
					Now: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now(),
						Units: 1,
					},
					Create: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(30 * time.Minute),
						Units: 0,
					},
				}}, nil)
			},
			ExpectedErr: director.ErrNoHypervisorAvailable.Error(),
		},
		"if there are already units, and we have a booking, it should use the available units": {
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:                  "9lypvd0p4",
				Status:              "Online",
				OnlyForced:          false,
				Buffering:           false,
				BookingsEndTime:     time.Now().Add(1 * time.Hour),
				OrchestratorManaged: true,
				DesktopsStarted:     8,
				CPU: isardvdi.OrchestratorResourceLoad{
					Total: 100,
					Used:  3,
					Free:  97,
				},
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 1031713,
					Used:  278237,
					Free:  753475,
				},
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					ID:         "9lypvd0p4-pci_0000_17_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  0,
					UsedUnits:  6,
				}, {
					ID:         "9lypvd0p4-pci_0000_31_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  4,
					UsedUnits:  2,
				}, {
					ID:         "9lypvd0p4-pci_0000_b1_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  6,
					UsedUnits:  0,
				}, {
					ID:         "9lypvd0p4-pci_0000_ca_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  6,
					UsedUnits:  0,
				}},
			}, {
				ID:                  "1esr7wpex",
				Status:              "Online",
				OnlyForced:          false,
				Buffering:           false,
				BookingsEndTime:     time.Now().Add(1 * time.Hour),
				OrchestratorManaged: true,
				DesktopsStarted:     8,
				CPU: isardvdi.OrchestratorResourceLoad{
					Total: 100,
					Used:  3,
					Free:  97,
				},
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 1031713,
					Used:  278237,
					Free:  753475,
				},
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					ID:         "1esr7wpex-pci_0000_17_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  6,
					UsedUnits:  0,
				}, {
					ID:         "1esr7wpex-pci_0000_31_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  1,
					UsedUnits:  5,
				}, {
					ID:         "1esr7wpex-pci_0000_b1_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  6,
					UsedUnits:  0,
				}, {
					ID:         "1esr7wpex-pci_0000_ca_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  6,
					UsedUnits:  0,
				}},
			}, {
				ID:                  "yuv3e1hwn",
				Status:              "Online",
				OnlyForced:          false,
				Buffering:           false,
				BookingsEndTime:     time.Now().Add(1 * time.Hour),
				OrchestratorManaged: true,
				DesktopsStarted:     8,
				CPU: isardvdi.OrchestratorResourceLoad{
					Total: 100,
					Used:  3,
					Free:  97,
				},
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 1031713,
					Used:  278237,
					Free:  753475,
				},
				GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
					ID:         "yuv3e1hwn-pci_0000_17_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  6,
					UsedUnits:  0,
				}, {
					ID:         "yuv3e1hwn-pci_0000_31_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  4,
					UsedUnits:  2,
				}, {
					ID:         "yuv3e1hwn-pci_0000_b1_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  0,
					UsedUnits:  6,
				}, {
					ID:         "yuv3e1hwn-pci_0000_ca_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  6,
					UsedUnits:  0,
				}},
			}},
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:           "1esr7wpex",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
				Cpu:          64,
				Ram:          1048576,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}, {
				Id:           "9lypvd0p4",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
				Cpu:          64,
				Ram:          1048576,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}, {
				Id:           "yuv3e1hwn",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
				Cpu:          64,
				Ram:          1048576,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}, {
				Id:           "new-hyper",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Cpu:          128,
				Ram:          1031701,
				Capabilities: []operationsv1.HypervisorCapabilities{operationsv1.HypervisorCapabilities_HYPERVISOR_CAPABILITIES_GPU},
				Gpus: []*operationsv1.HypervisorGPU{{
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}, {
					Brand: "NVIDIA",
					Model: "A10",
				}},
			}},
			PrepareAPI: func(api *apiMock.Client) {
				api.On("OrchestratorGPUBookingList", mock.AnythingOfType("context.backgroundCtx")).Return([]*isardvdi.OrchestratorGPUBooking{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now(),
						Units: 53,
					},
					Create: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(30 * time.Minute),
						Units: 1,
					},
					Destroy: isardvdi.OrchestratorGPUBookingTime{
						Time:  time.Now().Add(60 * time.Minute),
						Units: 1,
					},
				}}, nil)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)
			api := &apiMock.Client{}

			tc.PrepareAPI(api)

			chamaleon := director.NewChamaleon(&log, api)

			create, destroy, removeDeadRow, addDeadRow, err := chamaleon.NeedToScaleHypervisors(context.Background(), tc.AvailHypers, tc.Hypers)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedRemoveDeadRow, removeDeadRow)
			assert.Equal(tc.ExpectedCreateHypervisor, create)
			assert.Equal(tc.ExpectedAddDeadRow, addDeadRow)
			assert.Equal(tc.ExpectedDestroyHypervisor, destroy)
		})
	}
}
