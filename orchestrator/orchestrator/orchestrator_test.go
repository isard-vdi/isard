package orchestrator_test

import (
	"bytes"
	"context"
	"sync"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"go.nhat.io/grpcmock"
	gRPC "google.golang.org/grpc"
)

type silentT struct{}

func (silentT) Errorf(string, ...any) {}
func (silentT) Logf(string, ...any)   {}
func (silentT) FailNow()              {}

func TestStart(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		PrepareOperations func(*grpcmock.Server)
		PrepareAPI        func(context.CancelFunc, *apiv4.MockInvoker)
		CfgRata           cfg.DirectorRata
	}{
		"should remove an hypervisor from the dead row if it's available, instead of scaling up": {
			PrepareOperations: func(s *grpcmock.Server) {
				s.ExpectUnary("operations.v1.OperationsService/ListHypervisors").Return(&operationsv1.ListHypervisorsResponse{
					Hypervisors: []*operationsv1.ListHypervisorsResponseHypervisor{{
						Id:    "bm-e4-12",
						Cpu:   128,
						Ram:   2097152,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}, {
						Id:    "bm-e4-15",
						Cpu:   128,
						Ram:   2097152,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}, {
						Id:    "bm-e4-16",
						Cpu:   128,
						Ram:   2097152,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}},
				})
			},
			PrepareAPI: func(cancel context.CancelFunc, m *apiv4.MockInvoker) {
				oHypers := []apiv4.OrchestratorHypervisor{{
					ID:                  "bm-e4-12",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NilDateTime{Null: true},
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: true,
					GpuOnly:             false,
					DesktopsStarted:     234,
					MinFreeMemGB:        200,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  27,
						Free:  73,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2051898,
						Used:  1216615,
						Free:  835282,
					},
				}, {
					ID:                  "gpu-a10-2",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NilDateTime{Null: true},
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: false,
					GpuOnly:             false,
					DesktopsStarted:     70,
					MinFreeMemGB:        100,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  30,
						Free:  70,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1031700,
						Used:  461632,
						Free:  570067,
					},
					Gpus: []apiv4.OrchestratorHypervisorGPU{{
						ID:         "gpu-a10-2-pci_0000_31_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "2Q",
						TotalUnits: 12,
						FreeUnits:  12,
						UsedUnits:  0,
					}, {
						ID:         "gpu-a10-2-pci_0000_ca_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "4Q",
						TotalUnits: 6,
						FreeUnits:  6,
						UsedUnits:  0,
					}, {
						ID:         "gpu-a10-2-pci_0000_b1_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "2Q",
						TotalUnits: 12,
						FreeUnits:  12,
						UsedUnits:  0,
					}, {
						ID:         "gpu-a10-2-pci_0000_17_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "4Q",
						TotalUnits: 6,
						FreeUnits:  6,
						UsedUnits:  0,
					}},
				}, {
					ID:                  "bm-e4-15",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(1 * time.Hour)),
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: true,
					GpuOnly:             false,
					DesktopsStarted:     30,
					MinFreeMemGB:        200,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  1,
						Free:  99,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2051898,
						Used:  10727,
						Free:  2041170,
					},
				}}

				m.On("AdminOrchestratorHypervisorsList", mock.AnythingOfType("*context.cancelCtx")).Return(
					func(ctx context.Context) (apiv4.AdminOrchestratorHypervisorsListRes, error) {
						res := apiv4.AdminOrchestratorHypervisorsListOKApplicationJSON(oHypers)
						return &res, nil
					},
				)

				m.On("AdminOrchestratorDeadRowReset", mock.AnythingOfType("*context.timerCtx"), apiv4.AdminOrchestratorDeadRowResetParams{HypervisorID: "bm-e4-15"}).Run(func(args mock.Arguments) {
					oHypers[2].OnlyForced = false
					oHypers[2].DestroyTime = apiv4.NilDateTime{Null: true}
				}).Return(&apiv4.AdminOrchestratorDeadRowResetNoContent{}, nil)
			},
			CfgRata: cfg.DirectorRata{
				MinRAMLimitPercent: 150,
				MinRAMLimitMargin:  1126400,
				MaxRAMLimitPercent: 150,
				MaxRAMLimitMargin:  1331200,
				HyperMinRAM:        41200,
				HyperMaxRAM:        102400,
			},
		},
		"should destroy an hypervisor if required": {
			PrepareOperations: func(s *grpcmock.Server) {
				list := s.ExpectUnary("operations.v1.OperationsService/ListHypervisors")
				list.Return(&operationsv1.ListHypervisorsResponse{
					Hypervisors: []*operationsv1.ListHypervisorsResponseHypervisor{{
						Id:    "bm-e2-11",
						Cpu:   64,
						Ram:   524288,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}, {
						Id:    "bm-e2-12",
						Cpu:   64,
						Ram:   524288,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}, {
						Id:    "bm-e2-13",
						Cpu:   64,
						Ram:   524288,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}, {
						Id:    "bm-e2-14",
						Cpu:   64,
						Ram:   524288,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}, {
						Id:    "bm-e4-11",
						Cpu:   128,
						Ram:   2097152,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}, {
						Id:    "bm-e4-12",
						Cpu:   128,
						Ram:   2097152,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}, {
						Id:    "bm-e4-13",
						Cpu:   128,
						Ram:   2097152,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
					}, {
						Id:    "bm-e4-16",
						Cpu:   128,
						Ram:   2097152,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
					}, {
						Id:    "bm-std3-11",
						Cpu:   64,
						Ram:   1048576,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
					}, {
						Id:    "bm-std3-12",
						Cpu:   64,
						Ram:   1048576,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}, {
						Id:    "bm-std3-13",
						Cpu:   64,
						Ram:   1048576,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
					}, {
						Id:    "bm-std3-14",
						Cpu:   64,
						Ram:   1048576,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
					}, {
						Id:    "bm-std3-15",
						Cpu:   64,
						Ram:   1048576,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
					}, {
						Id:    "bm-e4-15",
						Cpu:   128,
						Ram:   2097152,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}},
				})
				list.Once()

				destroy := s.ExpectServerStream("operations.v1.OperationsService/DestroyHypervisors")
				destroy.Run(func(ctx context.Context, req any, s gRPC.ServerStream) error {
					msg1 := &operationsv1.DestroyHypervisorsResponse{
						State: operationsv1.OperationState_OPERATION_STATE_ACTIVE,
					}
					msg2 := &operationsv1.DestroyHypervisorsResponse{
						State: operationsv1.OperationState_OPERATION_STATE_COMPLETED,
					}

					if err := s.SendMsg(msg1); err != nil {
						return err
					}
					if err := s.SendMsg(msg2); err != nil {
						return err
					}

					return nil
				})
				destroy.Once()
			},
			PrepareAPI: func(cancel context.CancelFunc, m *apiv4.MockInvoker) {
				oHypers := []apiv4.OrchestratorHypervisor{{
					ID:                  "bm-e2-11",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NewNilDateTime(time.Date(2024, 2, 14, 23, 12, 19, 0, time.UTC)),
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: true,
					GpuOnly:             false,
					DesktopsStarted:     27,
					MinFreeMemGB:        50,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  3,
						Free:  97,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 515855,
						Used:  119794,
						Free:  396060,
					},
				}, {
					ID:                  "bm-e2-12",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NewNilDateTime(time.Date(2024, 2, 14, 23, 12, 30, 0, time.UTC)),
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: true,
					GpuOnly:             false,
					DesktopsStarted:     20,
					MinFreeMemGB:        50,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  2,
						Free:  98,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 515855,
						Used:  70115,
						Free:  445739,
					},
				}, {
					ID:                  "bm-e4-12",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NewNilDateTime(time.Date(2024, 2, 14, 21, 56, 55, 0, time.UTC)),
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: true,
					GpuOnly:             false,
					DesktopsStarted:     6,
					MinFreeMemGB:        200,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  1,
						Free:  99,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2051898,
						Used:  38185,
						Free:  2013712,
					},
				}, {
					ID:                  "bm-e4-11",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NewNilDateTime(time.Date(2024, 2, 14, 22, 45, 5, 0, time.UTC)),
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: true,
					GpuOnly:             false,
					DesktopsStarted:     27,
					MinFreeMemGB:        200,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  3,
						Free:  97,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2051898,
						Used:  153885,
						Free:  1898012,
					},
				}, {
					ID:                  "bm-e2-13",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NewNilDateTime(time.Date(2024, 2, 15, 1, 2, 11, 0, time.UTC)),
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: true,
					GpuOnly:             false,
					DesktopsStarted:     40,
					MinFreeMemGB:        50,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  10,
						Free:  90,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 515855,
						Used:  230584,
						Free:  285271,
					},
				}, {
					ID:                  "bm-e2-14",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NewNilDateTime(time.Date(2024, 2, 15, 1, 17, 52, 0, time.UTC)),
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: true,
					GpuOnly:             false,
					DesktopsStarted:     20,
					MinFreeMemGB:        50,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  6,
						Free:  94,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 515855,
						Used:  127595,
						Free:  388260,
					},
				}, {
					ID:                  "bm-std3-11",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NilDateTime{Null: true},
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: false,
					GpuOnly:             false,
					DesktopsStarted:     0,
					MinFreeMemGB:        100,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  1,
						Free:  99,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1031700,
						Used:  7441,
						Free:  1024258,
					},
				}, {
					ID:                  "bm-std3-12",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NewNilDateTime(time.Date(2024, 2, 14, 22, 45, 16, 0, time.UTC)),
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: true,
					GpuOnly:             false,
					DesktopsStarted:     49,
					MinFreeMemGB:        100,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  5,
						Free:  95,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1031700,
						Used:  201767,
						Free:  829932,
					},
				}, {
					ID:                  "gpu-a10-2",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NilDateTime{Null: true},
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: false,
					GpuOnly:             false,
					DesktopsStarted:     89,
					MinFreeMemGB:        100,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  20,
						Free:  80,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1031700,
						Used:  498174,
						Free:  533525,
					},
					Gpus: []apiv4.OrchestratorHypervisorGPU{{
						ID:         "gpu-a10-2-pci_0000_31_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "2Q",
						TotalUnits: 12,
						FreeUnits:  12,
						UsedUnits:  0,
					}, {
						ID:         "gpu-a10-2-pci_0000_ca_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "4Q",
						TotalUnits: 6,
						FreeUnits:  6,
						UsedUnits:  0,
					}, {
						ID:         "gpu-a10-2-pci_0000_b1_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "2Q",
						TotalUnits: 12,
						FreeUnits:  12,
						UsedUnits:  0,
					}, {
						ID:         "gpu-a10-2-pci_0000_17_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "4Q",
						TotalUnits: 6,
						FreeUnits:  6,
						UsedUnits:  0,
					}},
				}}

				m.On("AdminOrchestratorHypervisorsList", mock.AnythingOfType("*context.cancelCtx")).Return(
					func(ctx context.Context) (apiv4.AdminOrchestratorHypervisorsListRes, error) {
						res := apiv4.AdminOrchestratorHypervisorsListOKApplicationJSON(oHypers)
						return &res, nil
					},
				)

				m.On("AdminOrchestratorStopDesktops", mock.AnythingOfType("*context.timerCtx"), apiv4.AdminOrchestratorStopDesktopsParams{HypervisorID: "bm-e2-11"}).Return(&apiv4.AdminOrchestratorStopDesktopsNoContent{}, nil)
			},
			CfgRata: cfg.DirectorRata{
				MinRAMLimitPercent: 150,
				MinRAMLimitMargin:  0,
				MaxRAMLimitPercent: 150,
				MaxRAMLimitMargin:  0,
				HyperMinRAM:        41200,
				HyperMaxRAM:        102400,
			},
		},
		"should remove an hypervisor from only forced instead of scaling up": {
			PrepareOperations: func(s *grpcmock.Server) {
				s.ExpectUnary("operations.v1.OperationsService/ListHypervisors").Return(&operationsv1.ListHypervisorsResponse{
					Hypervisors: []*operationsv1.ListHypervisorsResponseHypervisor{{
						Id:    "bm-e4-12",
						Cpu:   128,
						Ram:   2097152,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}, {
						Id:    "bm-e4-15",
						Cpu:   128,
						Ram:   2097152,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}, {
						Id:    "bm-e4-16",
						Cpu:   128,
						Ram:   2097152,
						State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_DESTROY,
					}},
				})
			},
			PrepareAPI: func(cancel context.CancelFunc, m *apiv4.MockInvoker) {
				oHypers := []apiv4.OrchestratorHypervisor{{
					ID:                  "bm-e4-12",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NilDateTime{Null: true},
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: true,
					GpuOnly:             false,
					DesktopsStarted:     234,
					MinFreeMemGB:        200,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  27,
						Free:  73,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2051898,
						Used:  1216615,
						Free:  835282,
					},
				}, {
					ID:                  "gpu-a10-2",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NilDateTime{Null: true},
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: false,
					GpuOnly:             false,
					DesktopsStarted:     70,
					MinFreeMemGB:        100,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  30,
						Free:  70,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1031700,
						Used:  461632,
						Free:  570067,
					},
					Gpus: []apiv4.OrchestratorHypervisorGPU{{
						ID:         "gpu-a10-2-pci_0000_31_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "2Q",
						TotalUnits: 12,
						FreeUnits:  12,
						UsedUnits:  0,
					}, {
						ID:         "gpu-a10-2-pci_0000_ca_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "4Q",
						TotalUnits: 6,
						FreeUnits:  6,
						UsedUnits:  0,
					}, {
						ID:         "gpu-a10-2-pci_0000_b1_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "2Q",
						TotalUnits: 12,
						FreeUnits:  12,
						UsedUnits:  0,
					}, {
						ID:         "gpu-a10-2-pci_0000_17_00_0",
						Brand:      "NVIDIA",
						Model:      "A10",
						Profile:    "4Q",
						TotalUnits: 6,
						FreeUnits:  6,
						UsedUnits:  0,
					}},
				}, {
					ID:                  "bm-e4-15",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NilDateTime{Null: true},
					BookingsEndTime:     apiv4.NilDateTime{Null: true},
					OrchestratorManaged: true,
					GpuOnly:             false,
					DesktopsStarted:     0,
					MinFreeMemGB:        200,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  1,
						Free:  99,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2051898,
						Used:  10727,
						Free:  2041170,
					},
				}}

				m.On("AdminOrchestratorHypervisorsList", mock.AnythingOfType("*context.cancelCtx")).Return(
					func(ctx context.Context) (apiv4.AdminOrchestratorHypervisorsListRes, error) {
						res := apiv4.AdminOrchestratorHypervisorsListOKApplicationJSON(oHypers)
						return &res, nil
					},
				)

				m.On("AdminOrchestratorOnlyForcedSet", mock.AnythingOfType("*context.timerCtx"), &apiv4.OrchestratorOnlyForcedData{OnlyForced: false}, apiv4.AdminOrchestratorOnlyForcedSetParams{HypervisorID: "bm-e4-15"}).Run(func(args mock.Arguments) {
					oHypers[2].OnlyForced = false
				}).Return(&apiv4.AdminOrchestratorOnlyForcedSetNoContent{}, nil)
			},
			CfgRata: cfg.DirectorRata{
				MinRAMLimitPercent: 150,
				MinRAMLimitMargin:  1126400,
				MaxRAMLimitPercent: 150,
				MaxRAMLimitMargin:  1331200,
				HyperMinRAM:        41200,
				HyperMaxRAM:        102400,
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			assert := assert.New(t)
			require := require.New(t)
			ctx, cancel := context.WithCancel(t.Context())

			logBuf := &bytes.Buffer{}
			log := zerolog.New(logBuf).Level(zerolog.ErrorLevel)

			var wg sync.WaitGroup
			wg.Add(1)

			s := grpcmock.NewServer(
				grpcmock.RegisterService(operationsv1.RegisterOperationsServiceServer),
				tc.PrepareOperations,
			)
			t.Cleanup(func() {
				s.Close()
			})

			operationsCli, operationsConn, err := grpc.NewClient(ctx, operationsv1.NewOperationsServiceClient, s.Address())
			require.NoError(err)
			defer operationsConn.Close()

			apiCli := apiv4.NewMockInvoker(t)
			tc.PrepareAPI(cancel, apiCli)

			rata := director.NewRata(
				tc.CfgRata,
				false,
				&log,
				apiCli,
			)

			pollingInterval := 1 * time.Second

			o := orchestrator.New(&orchestrator.NewOrchestratorOpts{
				Log: &log,
				WG:  &wg,

				DryRun:            false,
				PollingInterval:   pollingInterval,
				OperationsTimeout: pollingInterval,

				Director:      rata,
				OperationsCli: operationsCli,

				CheckCfg: cfg.Check{
					Enabled: false,
				},
				CheckCli: nil,

				APICli: apiCli,
			})

			go o.Start(ctx)

			assert.Eventually(func() bool {
				return s.ExpectationsWereMet() == nil && apiCli.AssertExpectations(silentT{})
			}, 5*pollingInterval, 50*time.Millisecond, "mock expectations were not met within budget")

			apiCli.AssertExpectations(t)
			assert.NoError(s.ExpectationsWereMet())

			assert.Empty(logBuf)
		})
	}
}
