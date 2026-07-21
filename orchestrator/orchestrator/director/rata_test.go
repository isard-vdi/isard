package director_test

import (
	"os"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

func TestRataNeedToScaleHypervisors(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		AvailHypers               []*operationsv1.ListHypervisorsResponseHypervisor
		Hypers                    []*apiv4.OrchestratorHypervisor
		RataMinCPU                int
		RataMinRAM                int
		RataMaxCPU                int
		RataMaxRAM                int
		RataMinRAMLimitPercent    int
		RataMinRAMLimitMargin     int
		RataMaxRAMLimitPercent    int
		RataMaxRAMLimitMargin     int
		RataHyperMinRAM           int
		RataHyperMaxRAM           int
		ExpectedErr               string
		ExpectedRemoveDeadRow     []string
		ExpectedRemoveOnlyForced  []string
		ExpectedCreateHypervisor  *operationsv1.CreateHypervisorsRequest
		ExpectedAddDeadRow        []string
		ExpectedDestroyHypervisor *operationsv1.DestroyHypervisorsRequest
	}{
		"if there's enough RAM, it should return 0": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 300,
					Used:  150,
					Free:  150,
				},
			}},
			RataMinRAM: 100,
		},
		"if there's not enough RAM, it should return the ID of the hypervisor that needs to be created": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:    "testing",
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Ram:   5000,
			}, {
				Id:    "HUGE HYPERVISOR",
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Ram:   99999999,
			}, {
				Id:    "already",
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Ram:   300,
			}},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:         "already",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 300,
					Used:  200,
					Free:  100,
				},
			}},
			RataMinRAM: 500,
			ExpectedCreateHypervisor: &operationsv1.CreateHypervisorsRequest{
				Ids: []string{"testing"},
			},
		},
		"if some hyperviosrs are offline, buffer, GPU only, or only forced don't count them": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:    "testing",
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Ram:   5000,
			}, {
				Id:    "HUGE HYPERVISOR",
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Ram:   99999999,
			}, {
				Id:    "already",
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Ram:   300,
			}},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:         "already",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 300,
					Used:  200,
					Free:  100,
				},
			}, {
				ID:         "offline",
				Status:     apiv4.HypervisorStatusOffline,
				OnlyForced: false,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 1000,
					Used:  10,
					Free:  990,
				},
			}, {
				ID:             "buffering",
				Status:         apiv4.HypervisorStatusOnline,
				BufferingHyper: true,
				OnlyForced:     false,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 1000,
					Used:  10,
					Free:  990,
				},
			}, {
				ID:         "only forced",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 1000,
					Used:  10,
					Free:  990,
				},
			}, {
				ID:         "gpu only",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
				GpuOnly:    true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 1000,
					Used:  10,
					Free:  990,
				},
			}},
			RataMinRAM: 500,
			ExpectedCreateHypervisor: &operationsv1.CreateHypervisorsRequest{
				Ids: []string{"testing"},
			},
		},
		"if there's too much free RAM, it should add the biggest hypervisor that it can to the dead row": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "1",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 500,
					Used:  100,
					Free:  400,
				},
			}, {
				ID:                  "2",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          true,
				OrchestratorManaged: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 700,
					Used:  100,
					Free:  600,
				},
			}, {
				ID:                  "3",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 300,
					Used:  100,
					Free:  200,
				},
			}},
			RataMaxRAM:         300,
			ExpectedAddDeadRow: []string{"2"},
		},
		"if there's not enough RAM but there are hypervisors on the dead row, it should remove those from it": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:  "testing",
				Ram: 5000,
			}, {
				Id:  "HUGE HYPERVISOR",
				Ram: 99999999,
			}},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:         "existing-1",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 300,
					Used:  200,
					Free:  100,
				},
			}, {
				ID:                  "existing-2",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          true,
				DesktopsStarted:     20,
				OrchestratorManaged: true,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(time.Hour)),
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 3000,
					Used:  2000,
					Free:  1000,
				},
			}},
			RataMinRAM:            500,
			ExpectedRemoveDeadRow: []string{"existing-2"},
		},
		"if there's not enough RAM and there are multiple hypervisors on the dead row, it should remove the smallest hypervisor from it": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:  "testing",
				Ram: 5000,
			}, {
				Id:  "HUGE HYPERVISOR",
				Ram: 99999999,
			}},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "existing-1",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 300,
					Used:  200,
					Free:  100,
				},
			}, {
				ID:                  "existing-2",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          true,
				OrchestratorManaged: true,
				DesktopsStarted:     20,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(time.Hour)),
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 3000,
					Used:  2000,
					Free:  1000,
				},
			}, {
				ID:                  "existing-3",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          true,
				OrchestratorManaged: true,
				DesktopsStarted:     20,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(time.Hour)),
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 1000,
					Used:  300,
					Free:  700,
				},
			}},
			RataMinRAM:            500,
			ExpectedRemoveDeadRow: []string{"existing-3"},
		},
		"if there's an hypervisor that's been too much time on the dead row, KILL THEM!! >:(": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:         "1",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 500,
					Used:  400,
					Free:  100,
				},
			}, {
				ID:                  "2",
				Status:              apiv4.HypervisorStatusOnline,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(-2 * director.DeadRowDuration)),
				DesktopsStarted:     254,
				OnlyForced:          true,
				OrchestratorManaged: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 700,
					Used:  100,
					Free:  600,
				},
			}, {
				ID:         "3",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 500,
					Used:  250,
					Free:  250,
				},
			}},
			RataMinRAM: 300,
			ExpectedDestroyHypervisor: &operationsv1.DestroyHypervisorsRequest{
				Ids: []string{"2"},
			},
		},
		"if there's an hypervisor that's in the dead row and has 0 desktops started, KILL THEM!! >:(": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:         "1",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 500,
					Used:  400,
					Free:  100,
				},
			}, {
				ID:                  "2",
				Status:              apiv4.HypervisorStatusOnline,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(2 * director.DeadRowDuration)),
				DesktopsStarted:     0,
				OnlyForced:          true,
				OrchestratorManaged: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 700,
					Used:  100,
					Free:  600,
				},
			}, {
				ID:         "3",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 500,
					Used:  250,
					Free:  250,
				},
			}},
			RataMinRAM: 300,
			ExpectedDestroyHypervisor: &operationsv1.DestroyHypervisorsRequest{
				Ids: []string{"2"},
			},
		},
		"if there aren't enough ram, but there's a small hyper in the dead row and with it the system can work, remove it from the dead row": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "1",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          true,
				DestroyTime:         apiv4.NewNilDateTime(time.Now().Add(2 * director.DeadRowDuration)),
				OrchestratorManaged: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 600,
					Used:  400,
					Free:  200,
				},
			}, {
				ID:                  "2",
				Status:              apiv4.HypervisorStatusOnline,
				DesktopsStarted:     0,
				OnlyForced:          false,
				OrchestratorManaged: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 700,
					Used:  100,
					Free:  600,
				},
			}},
			RataMinRAM:            700,
			ExpectedRemoveDeadRow: []string{"1"},
		},
		"regression test #1": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "bm-e4-01",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				DesktopsStarted:     10,
				MinFreeMemGB:        190,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 2051961,
					Used:  67556,
					Free:  1984404,
				},
			}, {
				ID:                  "bm-e2-02",
				Status:              apiv4.HypervisorStatusOnline,
				DesktopsStarted:     2,
				OnlyForced:          false,
				OrchestratorManaged: false,
				MinFreeMemGB:        47,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 515855,
					Used:  65620,
					Free:  450234,
				},
			}},
			RataMinRAMLimitPercent: 150,
			RataMinRAMLimitMargin:  1,
			RataMaxRAMLimitPercent: 150,
			RataMaxRAMLimitMargin:  112640,
			RataHyperMinRAM:        51200,
			RataHyperMaxRAM:        102400,
			ExpectedAddDeadRow:     []string{"bm-e4-01"},
		},
		"regression test #2": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "bm-e4-04",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				DesktopsStarted:     46,
				MinFreeMemGB:        180,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 2051975,
					Used:  232253,
					Free:  1819722,
				},
			}, {
				ID:                  "bm-e2-02",
				Status:              apiv4.HypervisorStatusOnline,
				DesktopsStarted:     18,
				OnlyForced:          false,
				OrchestratorManaged: false,
				MinFreeMemGB:        47,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 515855,
					Used:  125714,
					Free:  390140,
				},
			}},
			RataMinRAMLimitPercent: 150,
			RataMinRAMLimitMargin:  1,

			RataMaxRAMLimitPercent: 150,
			RataMaxRAMLimitMargin:  112640,

			RataHyperMinRAM: 51200,
			RataHyperMaxRAM: 102400,

			ExpectedAddDeadRow: []string{"bm-e4-04"},
		},
		"regression test #3": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "bm-e4-01",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				BufferingHyper:      false,
				DestroyTime:         apiv4.NilDateTime{Null: true},
				BookingsEndTime:     apiv4.NilDateTime{Null: true},
				OrchestratorManaged: true,
				GpuOnly:             false,
				DesktopsStarted:     57,
				MinFreeMemGB:        190,
				CPU: apiv4.OrchestratorResourceLoad{
					Total: 100,
					Used:  6,
					Free:  94,
				},
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 2051961,
					Used:  305801,
					Free:  1746160,
				},
			}, {
				ID:                  "bm-e2-02",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				BufferingHyper:      false,
				DestroyTime:         apiv4.NilDateTime{Null: true},
				BookingsEndTime:     apiv4.NilDateTime{Null: true},
				OrchestratorManaged: false,
				GpuOnly:             false,
				DesktopsStarted:     23,
				MinFreeMemGB:        47,
				CPU: apiv4.OrchestratorResourceLoad{
					Total: 100,
					Used:  7,
					Free:  93,
				},
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 515855,
					Used:  160998,
					Free:  354856,
				},
			}},
			RataMinRAMLimitPercent: 150,
			RataMinRAMLimitMargin:  1,

			RataMaxRAMLimitPercent: 150,
			RataMaxRAMLimitMargin:  112640,

			RataHyperMinRAM: 51200,
			RataHyperMaxRAM: 102400,

			ExpectedAddDeadRow: []string{"bm-e4-01"},
		},
		"should remove an hypervisor from only forced if it has enough resources instead of scaling up": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:         "1",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: false,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 500,
					Used:  400,
					Free:  100,
				},
			}, {
				ID:                  "2",
				Status:              apiv4.HypervisorStatusOnline,
				DestroyTime:         apiv4.NilDateTime{Null: true},
				DesktopsStarted:     0,
				OnlyForced:          true,
				OrchestratorManaged: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 700,
					Used:  100,
					Free:  600,
				},
			}},
			RataMinRAM:               300,
			ExpectedRemoveOnlyForced: []string{"2"},
		},
		"should scale up with the biggest hypervisor available if the required RAM is higher than any of the available hypervisors RAM": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:           "bm-e4-12",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Cpu:          128,
				Ram:          1097152,
				Capabilities: []operationsv1.HypervisorCapabilities{},
			}, {
				Id:           "bm-e4-16",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Cpu:          128,
				Ram:          1097152,
				Capabilities: []operationsv1.HypervisorCapabilities{},
			}, {
				Id:           "bm-e4-21",
				State:        operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
				Cpu:          128,
				Ram:          1097152,
				Capabilities: []operationsv1.HypervisorCapabilities{},
			}},
			Hypers:     []*apiv4.OrchestratorHypervisor{},
			RataMinRAM: 3287400,
			ExpectedCreateHypervisor: &operationsv1.CreateHypervisorsRequest{
				Ids: []string{"bm-e4-12"},
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			log := zerolog.New(os.Stdout)

			rata := director.NewRata(cfg.DirectorRata{
				MinCPU:             tc.RataMinCPU,
				MinRAM:             tc.RataMinRAM,
				MaxCPU:             tc.RataMaxCPU,
				MaxRAM:             tc.RataMaxRAM,
				MinRAMLimitPercent: tc.RataMinRAMLimitPercent,
				MinRAMLimitMargin:  tc.RataMinRAMLimitMargin,
				MaxRAMLimitPercent: tc.RataMaxRAMLimitPercent,
				MaxRAMLimitMargin:  tc.RataMaxRAMLimitMargin,
				HyperMinRAM:        tc.RataHyperMinRAM,
				HyperMaxRAM:        tc.RataHyperMaxRAM,
			}, false, &log, nil)

			scale, err := rata.NeedToScaleHypervisors(t.Context(), tc.AvailHypers, tc.Hypers)

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

func TestRataExtraOperations(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareAPI  func(*apiv4.MockInvoker)
		Hypers      []*apiv4.OrchestratorHypervisor
		HyperMinCPU int
		HyperMinRAM int
		HyperMaxRAM int
		ExpectedErr string
	}{
		"if there are enough resources, it shouldn't do anything": {
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:     "first",
				Status: apiv4.HypervisorStatusOffline,
				RAM: apiv4.OrchestratorResourceLoad{
					Free: 10,
				},
			}, {
				ID:     "second",
				Status: apiv4.HypervisorStatusOnline,
				RAM: apiv4.OrchestratorResourceLoad{
					Free: 60,
				},
			}},
			HyperMinRAM: 50,
		},
		"if there's not enough RAM, it should set the hypervisor to only forced": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.Mock.On("AdminOrchestratorOnlyForcedSet", mock.AnythingOfType("*context.cancelCtx"), &apiv4.OrchestratorOnlyForcedData{OnlyForced: true}, apiv4.AdminOrchestratorOnlyForcedSetParams{HypervisorID: "second"}).Return(&apiv4.AdminOrchestratorOnlyForcedSetNoContent{}, nil)
			},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "first",
				Status:              apiv4.HypervisorStatusOffline,
				OrchestratorManaged: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Free: 10,
				},
			}, {
				ID:                  "second",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Free: 30,
				},
			}},
			HyperMinRAM: 50,
		},
		"if there's too much free RAM, it should remove the hypervisor from only forced": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.Mock.On("AdminOrchestratorOnlyForcedSet", mock.AnythingOfType("*context.cancelCtx"), &apiv4.OrchestratorOnlyForcedData{OnlyForced: false}, apiv4.AdminOrchestratorOnlyForcedSetParams{HypervisorID: "second"}).Return(&apiv4.AdminOrchestratorOnlyForcedSetNoContent{}, nil)
			},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "first",
				Status:              apiv4.HypervisorStatusOffline,
				OrchestratorManaged: true,
				DesktopsStarted:     1312,
				RAM: apiv4.OrchestratorResourceLoad{
					Free: 10,
				},
			}, {
				ID:                  "second",
				OnlyForced:          true,
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: true,
				DesktopsStarted:     1312,
				RAM: apiv4.OrchestratorResourceLoad{
					Free: 200,
				},
			}},
			HyperMinRAM: 30,
			HyperMaxRAM: 150,
		},
		"regresssion test #1": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.Mock.On("AdminOrchestratorOnlyForcedSet", mock.AnythingOfType("*context.cancelCtx"), &apiv4.OrchestratorOnlyForcedData{OnlyForced: true}, apiv4.AdminOrchestratorOnlyForcedSetParams{HypervisorID: "bm-e2-03"}).Return(&apiv4.AdminOrchestratorOnlyForcedSetNoContent{}, nil)
				c.Mock.On("AdminOrchestratorOnlyForcedSet", mock.AnythingOfType("*context.cancelCtx"), &apiv4.OrchestratorOnlyForcedData{OnlyForced: true}, apiv4.AdminOrchestratorOnlyForcedSetParams{HypervisorID: "bm-e2-01"}).Return(&apiv4.AdminOrchestratorOnlyForcedSetNoContent{}, nil)
			},
			Hypers: []*apiv4.OrchestratorHypervisor{
				{
					ID:                  "bm-e4-02",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					OrchestratorManaged: true,
					DesktopsStarted:     39,
					MinFreeMemGB:        190,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  7,
						Free:  93,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2051961,
						Used:  249909,
						Free:  1802051,
					},
				},
				{
					ID:                  "bm-e4-01",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NewNilDateTime(time.Now()),
					OrchestratorManaged: true,
					DesktopsStarted:     266,
					MinFreeMemGB:        190,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  23,
						Free:  77,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2051961,
						Used:  1540080,
						Free:  511881,
					},
				},
				{
					ID:                  "bm-e2-03",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					OrchestratorManaged: true,
					DesktopsStarted:     70,
					MinFreeMemGB:        47,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  30,
						Free:  70,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 515855,
						Used:  407554,
						Free:  108300,
					},
				},
				{
					ID:                  "bm-e2-01",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					OrchestratorManaged: true,
					DesktopsStarted:     77,
					MinFreeMemGB:        47,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  27,
						Free:  73,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 515855,
						Used:  409618,
						Free:  106237,
					},
				},
				{
					ID:                  "bm-e2-02",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					OrchestratorManaged: false,
					DesktopsStarted:     64,
					MinFreeMemGB:        47,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  25,
						Free:  75,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 515855,
						Used:  441597,
						Free:  74258,
					},
				},
			},
			HyperMinRAM: 92160,
			HyperMaxRAM: 153600,
		},
		"regression test #2": {
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			Hypers: []*apiv4.OrchestratorHypervisor{
				{
					ID:                  "bm-e4-02",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					OrchestratorManaged: true,
					DesktopsStarted:     39,
					MinFreeMemGB:        190,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  7,
						Free:  93,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2051961,
						Used:  249909,
						Free:  1802051,
					},
				},
				{
					ID:                  "bm-e4-01",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					DestroyTime:         apiv4.NewNilDateTime(time.Now()),
					OrchestratorManaged: true,
					DesktopsStarted:     266,
					MinFreeMemGB:        190,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  23,
						Free:  77,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2051961,
						Used:  1540080,
						Free:  511881,
					},
				},
				{
					ID:                  "bm-e2-03",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					OrchestratorManaged: true,
					DesktopsStarted:     70,
					MinFreeMemGB:        47,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  30,
						Free:  70,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 515855,
						Used:  407554,
						Free:  108300,
					},
				},
				{
					ID:                  "bm-e2-01",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          true,
					BufferingHyper:      false,
					OrchestratorManaged: true,
					DesktopsStarted:     77,
					MinFreeMemGB:        47,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  27,
						Free:  73,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 515855,
						Used:  409618,
						Free:  106237,
					},
				},
				{
					ID:                  "bm-e2-02",
					Status:              apiv4.HypervisorStatusOnline,
					OnlyForced:          false,
					BufferingHyper:      false,
					OrchestratorManaged: false,
					DesktopsStarted:     64,
					MinFreeMemGB:        47,
					CPU: apiv4.OrchestratorResourceLoad{
						Total: 100,
						Used:  25,
						Free:  75,
					},
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 515855,
						Used:  441597,
						Free:  74258,
					},
				},
			},
			HyperMinRAM: 92160,
			HyperMaxRAM: 153600,
		},
		"should not remove an hypervisor from only forced if it has no desktops (will be removed by NeedsToScaleHypervisors)": {
			PrepareAPI: func(*apiv4.MockInvoker) {},
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "gpu-a10-01",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				BufferingHyper:      false,
				DestroyTime:         apiv4.NilDateTime{Null: true},
				BookingsEndTime:     apiv4.NilDateTime{Null: true},
				OrchestratorManaged: false,
				GpuOnly:             false,
				DesktopsStarted:     60,
				MinFreeMemGB:        100,
				CPU: apiv4.OrchestratorResourceLoad{
					Total: 100,
					Used:  17,
					Free:  83,
				},
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 1031694,
					Used:  519912,
					Free:  511782,
				},
				Gpus: []apiv4.OrchestratorHypervisorGPU{{
					ID:         "gpu-a10-01-pci_0000_ca_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "2Q",
					TotalUnits: 12,
					FreeUnits:  12,
					UsedUnits:  0,
				}, {
					ID:         "gpu-a10-01-pci_0000_17_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "2Q",
					TotalUnits: 12,
					FreeUnits:  12,
					UsedUnits:  0,
				}, {
					ID:         "gpu-a10-01-pci_0000_31_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "6Q",
					TotalUnits: 6,
					FreeUnits:  6,
					UsedUnits:  0,
				}, {}, {
					ID:         "gpu-a10-01-pci_0000_b1_00_0",
					Brand:      "NVIDIA",
					Model:      "A10",
					Profile:    "6Q",
					TotalUnits: 6,
					FreeUnits:  6,
					UsedUnits:  0,
				}},
			}, {
				ID:                  "bm-e2-11",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          true,
				BufferingHyper:      false,
				DestroyTime:         apiv4.NilDateTime{Null: true},
				BookingsEndTime:     apiv4.NilDateTime{Null: true},
				OrchestratorManaged: true,
				GpuOnly:             false,
				DesktopsStarted:     0,
				MinFreeMemGB:        50,
				CPU: apiv4.OrchestratorResourceLoad{
					Total: 100,
					Used:  2,
					Free:  98,
				},
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 515850,
					Used:  3538,
					Free:  512311,
				},
			}, {
				ID:                  "bm-e2-12",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				BufferingHyper:      false,
				DestroyTime:         apiv4.NilDateTime{Null: true},
				BookingsEndTime:     apiv4.NilDateTime{Null: true},
				OrchestratorManaged: true,
				GpuOnly:             false,
				DesktopsStarted:     55,
				MinFreeMemGB:        50,
				CPU: apiv4.OrchestratorResourceLoad{
					Total: 100,
					Used:  18,
					Free:  81,
				},
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 515849,
					Used:  335477,
					Free:  180372,
				},
			}, {
				ID:                  "bm-e4-12",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          false,
				BufferingHyper:      false,
				DestroyTime:         apiv4.NilDateTime{Null: true},
				BookingsEndTime:     apiv4.NilDateTime{Null: true},
				OrchestratorManaged: true,
				GpuOnly:             false,
				DesktopsStarted:     202,
				MinFreeMemGB:        200,
				CPU: apiv4.OrchestratorResourceLoad{
					Total: 100,
					Used:  14,
					Free:  86,
				},
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 2051891,
					Used:  1300091,
					Free:  751799,
				},
			}, {
				ID:                  "bm-e4-16",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          true,
				BufferingHyper:      false,
				DestroyTime:         apiv4.NewNilDateTime(time.Now()),
				BookingsEndTime:     apiv4.NilDateTime{Null: true},
				OrchestratorManaged: true,
				GpuOnly:             false,
				DesktopsStarted:     156,
				MinFreeMemGB:        200,
				CPU: apiv4.OrchestratorResourceLoad{
					Total: 100,
					Used:  11,
					Free:  89,
				},
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 2051891,
					Used:  1118939,
					Free:  932951,
				},
			}, {
				ID:                  "e4-21",
				Status:              apiv4.HypervisorStatusOnline,
				OnlyForced:          true,
				BufferingHyper:      false,
				DestroyTime:         apiv4.NewNilDateTime(time.Now()),
				BookingsEndTime:     apiv4.NilDateTime{Null: true},
				OrchestratorManaged: true,
				GpuOnly:             false,
				DesktopsStarted:     240,
				MinFreeMemGB:        200,
				CPU: apiv4.OrchestratorResourceLoad{
					Total: 100,
					Used:  17,
					Free:  83,
				},
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 2051891,
					Used:  1466408,
					Free:  585482,
				},
			}},
			HyperMinRAM: 41200,
			HyperMaxRAM: 102400,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			log := zerolog.New(os.Stdout)
			api := apiv4.NewMockInvoker(t)

			tc.PrepareAPI(api)

			rata := director.NewRata(cfg.DirectorRata{
				HyperMinCPU: tc.HyperMinCPU,
				HyperMinRAM: tc.HyperMinRAM,
				HyperMaxRAM: tc.HyperMaxRAM,
			}, false, &log, api)

			err := rata.ExtraOperations(t.Context(), tc.Hypers)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			api.AssertExpectations(t)
		})
	}
}
