package director_test

import (
	"os"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

func TestChamaleonNeedToScaleHypervisors(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		AvailHypers               []*operationsv1.ListHypervisorsResponseHypervisor
		Hypers                    []*apiv4.OrchestratorHypervisor
		PrepareAPI                func(*apiv4.MockInvoker)
		ExpectedErr               string
		ExpectedRemoveDeadRow     []string
		ExpectedRemoveOnlyForced  []string
		ExpectedCreateHypervisor  *operationsv1.CreateHypervisorsRequest
		ExpectedAddDeadRow        []string
		ExpectedDestroyHypervisor *operationsv1.DestroyHypervisorsRequest
	}{
		"if there are enough units, it should return 0": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}},
			PrepareAPI: func(api *apiv4.MockInvoker) {
				bookings := apiv4.GetGpuBookingsForecastOKApplicationJSON([]apiv4.GpuForecastProfile{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: apiv4.GpuForecastUnit{
						Units: 5,
					},
					ToCreate: apiv4.GpuForecastUnit{
						Units: 7,
					},
					ToDestroy: apiv4.GpuForecastUnit{
						Units: 4,
					},
				}})
				api.On("GetGpuBookingsForecast", mock.AnythingOfType("*context.cancelCtx")).Return(&bookings, nil)
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
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:         "existing",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
			}},
			PrepareAPI: func(api *apiv4.MockInvoker) {
				bookings := apiv4.GetGpuBookingsForecastOKApplicationJSON([]apiv4.GpuForecastProfile{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: apiv4.GpuForecastUnit{
						Units: 5,
					},
					ToCreate: apiv4.GpuForecastUnit{
						Units: 7,
					},
					ToDestroy: apiv4.GpuForecastUnit{
						Units: 4,
					},
				}})
				api.On("GetGpuBookingsForecast", mock.AnythingOfType("*context.cancelCtx")).Return(&bookings, nil)
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
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:         "existing",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
			}},
			PrepareAPI: func(api *apiv4.MockInvoker) {
				bookings := apiv4.GetGpuBookingsForecastOKApplicationJSON([]apiv4.GpuForecastProfile{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: apiv4.GpuForecastUnit{
						Units: 8, // One A10 card has 6 4Q profiles
					},
					ToCreate: apiv4.GpuForecastUnit{
						Units: 9,
					},
					ToDestroy: apiv4.GpuForecastUnit{
						Units: 4,
					},
				}})
				api.On("GetGpuBookingsForecast", mock.AnythingOfType("*context.cancelCtx")).Return(&bookings, nil)
			},
			ExpectedCreateHypervisor: &operationsv1.CreateHypervisorsRequest{
				Ids: []string{"testing good 1", "testing good 2"},
			},
		},
		"if there's not too much free units, it should add the biggest hypervisor to the dead row": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "to keep",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 6,
					FreeUnits:  5,
				}},
			}, {
				ID:                  "AMONGUS!",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
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
			PrepareAPI: func(api *apiv4.MockInvoker) {
				bookings := apiv4.GetGpuBookingsForecastOKApplicationJSON([]apiv4.GpuForecastProfile{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: apiv4.GpuForecastUnit{
						Units: 4, // One A10 card has 6 4Q profiles
					},
					ToCreate: apiv4.GpuForecastUnit{
						Units: 4,
					},
					ToDestroy: apiv4.GpuForecastUnit{
						Units: 4,
					},
				}})
				api.On("GetGpuBookingsForecast", mock.AnythingOfType("*context.cancelCtx")).Return(&bookings, nil)
			},
			ExpectedAddDeadRow: []string{"AMONGUS!"},
		},
		"if there's not enough units, but there are hypervisors on the dead row, if should remove those from it": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "destroy 1",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          true,
				OrchestratorManaged: true,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(-1 * time.Hour)),
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}, {
				ID:                  "destroy 2",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          true,
				OrchestratorManaged: true,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(1 * time.Hour)),
				DesktopsStarted:     0,
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
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
			PrepareAPI: func(api *apiv4.MockInvoker) {
				bookings := apiv4.GetGpuBookingsForecastOKApplicationJSON([]apiv4.GpuForecastProfile{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: apiv4.GpuForecastUnit{
						Units: 13,
					},
					ToCreate: apiv4.GpuForecastUnit{
						Units: 7,
					},
					ToDestroy: apiv4.GpuForecastUnit{
						Units: 8,
					},
				}})
				api.On("GetGpuBookingsForecast", mock.AnythingOfType("*context.cancelCtx")).Return(&bookings, nil)
			},
			ExpectedRemoveDeadRow: []string{"destroy 1", "destroy 2"},
		},
		"if there's an hypervisor that's been too much time on the dead row, KILL THEM!!! >:(": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "destroy 1",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}, {
				ID:                  "destroy 2",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          true,
				OrchestratorManaged: true,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(1 * time.Hour)),
				DesktopsStarted:     0,
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
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
			PrepareAPI: func(api *apiv4.MockInvoker) {
				bookings := apiv4.GetGpuBookingsForecastOKApplicationJSON([]apiv4.GpuForecastProfile{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: apiv4.GpuForecastUnit{
						Units: 4,
					},
					ToCreate: apiv4.GpuForecastUnit{
						Units: 3,
					},
					ToDestroy: apiv4.GpuForecastUnit{
						Units: 5,
					},
				}})
				api.On("GetGpuBookingsForecast", mock.AnythingOfType("*context.cancelCtx")).Return(&bookings, nil)
			},
			ExpectedDestroyHypervisor: &operationsv1.DestroyHypervisorsRequest{
				Ids: []string{"destroy 2"},
			},
		},
		"if there are multiple hypervisor that have been too much time on the dead row, have 0 desktops started or have exceeded the booking time, KILL THEM!!! >:(": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "destroy 1",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(-1 * time.Hour)),
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}, {
				ID:                  "non managed",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: false,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(-1 * time.Hour)),
				DesktopsStarted:     234,
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}, {
				ID:                  "destroy 2",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(1 * time.Hour)),
				DesktopsStarted:     0,
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}, {
				ID:                  "destroy 3",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(1 * time.Hour)),
				DesktopsStarted:     23,
				BookingsEndTime:     apiv4.NewNilDateTime(time.Now().Add(-1 * time.Hour)),
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "4Q",
					TotalUnits: 10,
					UsedUnits:  1,
					FreeUnits:  9,
				}},
			}},
			PrepareAPI: func(api *apiv4.MockInvoker) {
				bookings := apiv4.GetGpuBookingsForecastOKApplicationJSON([]apiv4.GpuForecastProfile{})
				api.On("GetGpuBookingsForecast", mock.AnythingOfType("*context.cancelCtx")).Return(&bookings, nil)
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
			Hypers: []*apiv4.OrchestratorHypervisor{{}},
			PrepareAPI: func(api *apiv4.MockInvoker) {
				bookings := apiv4.GetGpuBookingsForecastOKApplicationJSON([]apiv4.GpuForecastProfile{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "24Q",
					Now: apiv4.GpuForecastUnit{
						Units: 2,
					},
					ToCreate: apiv4.GpuForecastUnit{
						Units: 0,
					},
				}})
				api.On("GetGpuBookingsForecast", mock.AnythingOfType("*context.cancelCtx")).Return(&bookings, nil)
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
			Hypers: []*apiv4.OrchestratorHypervisor{{}},
			PrepareAPI: func(api *apiv4.MockInvoker) {
				bookings := apiv4.GetGpuBookingsForecastOKApplicationJSON([]apiv4.GpuForecastProfile{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "24Q",
					Now: apiv4.GpuForecastUnit{
						Units: 1,
					},
					ToCreate: apiv4.GpuForecastUnit{
						Units: 0,
					},
				}})
				api.On("GetGpuBookingsForecast", mock.AnythingOfType("*context.cancelCtx")).Return(&bookings, nil)
			},
			ExpectedErr: director.ErrNoHypervisorAvailable.Error(),
		},
		"if there are already units, and we have a booking, it should use the available units": {
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "9lypvd0p4",
				Status:              "Online",
				OnlyForced:          false,
				BufferingHyper:      false,
				BookingsEndTime:     apiv4.NewNilDateTime(time.Now().Add(1 * time.Hour)),
				OrchestratorManaged: true,
				DesktopsStarted:     8,
				CPU: apiv4.OrchestratorResourceLoad{
					Total: 100,
					Used:  3,
					Free:  97,
				},
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 1031713,
					Used:  278237,
					Free:  753475,
				},
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
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
				BufferingHyper:      false,
				BookingsEndTime:     apiv4.NewNilDateTime(time.Now().Add(1 * time.Hour)),
				OrchestratorManaged: true,
				DesktopsStarted:     8,
				CPU: apiv4.OrchestratorResourceLoad{
					Total: 100,
					Used:  3,
					Free:  97,
				},
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 1031713,
					Used:  278237,
					Free:  753475,
				},
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
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
				BufferingHyper:      false,
				BookingsEndTime:     apiv4.NewNilDateTime(time.Now().Add(1 * time.Hour)),
				OrchestratorManaged: true,
				DesktopsStarted:     8,
				CPU: apiv4.OrchestratorResourceLoad{
					Total: 100,
					Used:  3,
					Free:  97,
				},
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 1031713,
					Used:  278237,
					Free:  753475,
				},
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
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
			PrepareAPI: func(api *apiv4.MockInvoker) {
				bookings := apiv4.GetGpuBookingsForecastOKApplicationJSON([]apiv4.GpuForecastProfile{{
					Brand:   "NVIDIA",
					Model:   "A10",
					Profile: "4Q",
					Now: apiv4.GpuForecastUnit{
						Units: 53,
					},
					ToCreate: apiv4.GpuForecastUnit{
						Units: 1,
					},
					ToDestroy: apiv4.GpuForecastUnit{
						Units: 1,
					},
				}})
				api.On("GetGpuBookingsForecast", mock.AnythingOfType("*context.cancelCtx")).Return(&bookings, nil)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			log := zerolog.New(os.Stdout)
			api := apiv4.NewMockInvoker(t)

			tc.PrepareAPI(api)

			chamaleon := director.NewChamaleon(&log, api)

			scale, err := chamaleon.NeedToScaleHypervisors(t.Context(), tc.AvailHypers, tc.Hypers)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.ElementsMatch(tc.ExpectedRemoveDeadRow, scale.HypersToRemoveFromDeadRow)
			assert.ElementsMatch(tc.ExpectedRemoveOnlyForced, scale.HypersToRemoveFromOnlyForced)
			assert.Equal(tc.ExpectedCreateHypervisor, scale.Create)
			assert.ElementsMatch(tc.ExpectedAddDeadRow, scale.HypersToAddToDeadRow)
			assert.Equal(tc.ExpectedDestroyHypervisor, scale.Destroy)
		})
	}
}
