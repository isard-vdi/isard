package orchestrator_test

import (
	"bytes"
	"context"
	"sync"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi-sdk-go"
	apiMock "gitlab.com/isard/isardvdi-sdk-go/mock"
	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"google.golang.org/grpc"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"go.nhat.io/grpcmock"
)

func TestStart(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareOperations func(*grpcmock.Server)
		PrepareAPI        func(context.CancelFunc, *apiMock.Client)
		CfgRata           cfg.DirectorRata
	}{
		"should remove an hypervisor from only forced if it's available, instead of scaling up": {
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
			PrepareAPI: func(cancel context.CancelFunc, m *apiMock.Client) {
				hypers := []*isardvdi.OrchestratorHypervisor{{
					ID:                  "bm-e4-12",
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          false,
					Buffering:           false,
					DestroyTime:         time.Time{},
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: true,
					GPUOnly:             false,
					DesktopsStarted:     234,
					MinFreeMemGB:        200,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  27,
						Free:  73,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 2051898,
						Used:  1216615,
						Free:  835282,
					},
				}, {
					ID:                  "gpu-a10-2",
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          false,
					Buffering:           false,
					DestroyTime:         time.Time{},
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: false,
					GPUOnly:             false,
					DesktopsStarted:     70,
					MinFreeMemGB:        100,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  30,
						Free:  70,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1031700,
						Used:  461632,
						Free:  570067,
					},
					GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
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
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          true,
					Buffering:           false,
					DestroyTime:         time.Time{},
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: true,
					GPUOnly:             false,
					DesktopsStarted:     0,
					MinFreeMemGB:        200,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  1,
						Free:  99,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 2051898,
						Used:  10727,
						Free:  2041170,
					},
				}}

				m.On("OrchestratorHypervisorList", mock.AnythingOfType("*context.cancelCtx")).Return(hypers, nil)
				m.On("AdminHypervisorOnlyForced", mock.AnythingOfType("*context.cancelCtx"), "bm-e4-15", false).Run(func(args mock.Arguments) {
					hypers[2].OnlyForced = false
				}).Return(nil)
				m.On("OrchestratorHypervisorAddToDeadRow", mock.AnythingOfType("*context.timerCtx"), "bm-e4-12").Run(func(args mock.Arguments) {
					cancel()
				}).Return(time.Now(), nil)
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
				destroy.Run(func(ctx context.Context, req any, s grpc.ServerStream) error {

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
			PrepareAPI: func(cancel context.CancelFunc, m *apiMock.Client) {
				hypers := []*isardvdi.OrchestratorHypervisor{{
					ID:                  "bm-e2-11",
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          true,
					Buffering:           false,
					DestroyTime:         time.Date(2024, 2, 14, 23, 12, 19, 0, time.UTC),
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: true,
					GPUOnly:             false,
					DesktopsStarted:     27,
					MinFreeMemGB:        50,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  3,
						Free:  97,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 515855,
						Used:  119794,
						Free:  396060,
					},
				}, {
					ID:                  "bm-e2-12",
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          true,
					Buffering:           false,
					DestroyTime:         time.Date(2024, 2, 14, 23, 12, 30, 0, time.UTC),
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: true,
					GPUOnly:             false,
					DesktopsStarted:     20,
					MinFreeMemGB:        50,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  2,
						Free:  98,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 515855,
						Used:  70115,
						Free:  445739,
					},
				}, {
					ID:                  "bm-e4-12",
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          true,
					Buffering:           false,
					DestroyTime:         time.Date(2024, 2, 14, 21, 56, 55, 0, time.UTC),
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: true,
					GPUOnly:             false,
					DesktopsStarted:     6,
					MinFreeMemGB:        200,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  1,
						Free:  99,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 2051898,
						Used:  38185,
						Free:  2013712,
					},
				}, {
					ID:                  "bm-e4-11",
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          true,
					Buffering:           false,
					DestroyTime:         time.Date(2024, 2, 14, 22, 45, 5, 0, time.UTC),
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: true,
					GPUOnly:             false,
					DesktopsStarted:     27,
					MinFreeMemGB:        200,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  3,
						Free:  97,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 2051898,
						Used:  153885,
						Free:  1898012,
					},
				}, {
					ID:                  "bm-e2-13",
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          true,
					Buffering:           false,
					DestroyTime:         time.Date(2024, 2, 15, 1, 2, 11, 0, time.UTC),
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: true,
					GPUOnly:             false,
					DesktopsStarted:     40,
					MinFreeMemGB:        50,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  10,
						Free:  90,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 515855,
						Used:  230584,
						Free:  285271,
					},
				}, {
					ID:                  "bm-e2-14",
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          true,
					Buffering:           false,
					DestroyTime:         time.Date(2024, 2, 15, 1, 17, 52, 0, time.UTC),
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: true,
					GPUOnly:             false,
					DesktopsStarted:     20,
					MinFreeMemGB:        50,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  6,
						Free:  94,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 515855,
						Used:  127595,
						Free:  388260,
					},
				}, {
					ID:                  "bm-std3-11",
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          true,
					Buffering:           false,
					DestroyTime:         time.Time{},
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: false,
					GPUOnly:             false,
					DesktopsStarted:     0,
					MinFreeMemGB:        100,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  1,
						Free:  99,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1031700,
						Used:  7441,
						Free:  1024258,
					},
				}, {
					ID:                  "bm-std3-12",
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          true,
					Buffering:           false,
					DestroyTime:         time.Date(2024, 2, 14, 22, 45, 16, 0, time.UTC),
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: true,
					GPUOnly:             false,
					DesktopsStarted:     49,
					MinFreeMemGB:        100,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  5,
						Free:  95,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1031700,
						Used:  201767,
						Free:  829932,
					},
				}, {
					ID:                  "gpu-a10-2",
					Status:              isardvdi.HypervisorStatusOnline,
					OnlyForced:          false,
					Buffering:           false,
					DestroyTime:         time.Time{},
					BookingsEndTime:     time.Time{},
					OrchestratorManaged: false,
					GPUOnly:             false,
					DesktopsStarted:     89,
					MinFreeMemGB:        100,
					CPU: isardvdi.OrchestratorResourceLoad{
						Total: 100,
						Used:  20,
						Free:  80,
					},
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1031700,
						Used:  498174,
						Free:  533525,
					},
					GPUs: []*isardvdi.OrchestratorHypervisorGPU{{
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

				m.On("OrchestratorHypervisorList", mock.AnythingOfType("*context.cancelCtx")).Return(hypers, nil)
				m.On("OrchestratorHypervisorStopDesktops", mock.AnythingOfType("*context.timerCtx"), "bm-e2-11").Return(nil)
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
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx, cancel := context.WithCancel(context.Background())

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

			operationsConn, err := grpc.DialContext(ctx, s.Address(), grpc.WithInsecure())
			require.NoError(err)
			defer operationsConn.Close()

			operations := operationsv1.NewOperationsServiceClient(operationsConn)

			apiCli := &apiMock.Client{}
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
				OperationsCli: operations,

				CheckCfg: cfg.Check{
					Enabled: false,
				},
				CheckCli: nil,

				APICli: apiCli,
			})

			go o.Start(ctx)

			time.Sleep(pollingInterval + 500*time.Millisecond)

			apiCli.AssertExpectations(t)
			assert.NoError(s.ExpectationsWereMet())

			assert.Empty(logBuf)
		})
	}
}
