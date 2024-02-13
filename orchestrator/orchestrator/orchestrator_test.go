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
