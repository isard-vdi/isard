package director_test

import (
	"os"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/director"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/model"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/model/testhelper"
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
		Hypers                    []*model.Hypervisor
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
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithRAM(300, 150, 150),
				),
			},
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
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("already"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithRAM(300, 200, 100),
				),
			},
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
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("already"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithRAM(300, 200, 100),
				),
				testhelper.Hypervisor(
					testhelper.WithID("offline"),
					testhelper.WithStatus(model.HypervisorStatusOffline),
					testhelper.WithOnlyForced(false),
					testhelper.WithRAM(1000, 10, 990),
				),
				testhelper.Hypervisor(
					testhelper.WithID("buffering"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithBuffering(true),
					testhelper.WithOnlyForced(false),
					testhelper.WithRAM(1000, 10, 990),
				),
				testhelper.Hypervisor(
					testhelper.WithID("only forced"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(true),
					testhelper.WithRAM(1000, 10, 990),
				),
				testhelper.Hypervisor(
					testhelper.WithID("gpu only"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithGpuOnly(true),
					testhelper.WithRAM(1000, 10, 990),
				),
			},
			RataMinRAM: 500,
			ExpectedCreateHypervisor: &operationsv1.CreateHypervisorsRequest{
				Ids: []string{"testing"},
			},
		},
		"if there's too much free RAM, it should add the biggest hypervisor that it can to the dead row": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("1"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithRAM(500, 100, 400),
				),
				testhelper.Hypervisor(
					testhelper.WithID("2"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(true),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithRAM(700, 100, 600),
				),
				testhelper.Hypervisor(
					testhelper.WithID("3"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithRAM(300, 100, 200),
				),
			},
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
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("existing-1"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithRAM(300, 200, 100),
				),
				testhelper.Hypervisor(
					testhelper.WithID("existing-2"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(true),
					testhelper.WithDesktopsStarted(20),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDestroyTime(time.Now().Add(time.Hour)),
					testhelper.WithRAM(3000, 2000, 1000),
				),
			},
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
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("existing-1"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithRAM(300, 200, 100),
				),
				testhelper.Hypervisor(
					testhelper.WithID("existing-2"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(true),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(20),
					testhelper.WithDestroyTime(time.Now().Add(time.Hour)),
					testhelper.WithRAM(3000, 2000, 1000),
				),
				testhelper.Hypervisor(
					testhelper.WithID("existing-3"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(true),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(20),
					testhelper.WithDestroyTime(time.Now().Add(time.Hour)),
					testhelper.WithRAM(1000, 300, 700),
				),
			},
			RataMinRAM:            500,
			ExpectedRemoveDeadRow: []string{"existing-3"},
		},
		"if there's an hypervisor that's been too much time on the dead row, KILL THEM!! >:(": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("1"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithRAM(500, 400, 100),
				),
				testhelper.Hypervisor(
					testhelper.WithID("2"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithDestroyTime(time.Now().Add(-2*director.DeadRowDuration)),
					testhelper.WithDesktopsStarted(254),
					testhelper.WithOnlyForced(true),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithRAM(700, 100, 600),
				),
				testhelper.Hypervisor(
					testhelper.WithID("3"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithRAM(500, 250, 250),
				),
			},
			RataMinRAM: 300,
			ExpectedDestroyHypervisor: &operationsv1.DestroyHypervisorsRequest{
				Ids: []string{"2"},
			},
		},
		"if there's an hypervisor that's in the dead row and has 0 desktops started, KILL THEM!! >:(": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("1"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithRAM(500, 400, 100),
				),
				testhelper.Hypervisor(
					testhelper.WithID("2"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithDestroyTime(time.Now().Add(2*director.DeadRowDuration)),
					testhelper.WithDesktopsStarted(0),
					testhelper.WithOnlyForced(true),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithRAM(700, 100, 600),
				),
				testhelper.Hypervisor(
					testhelper.WithID("3"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithRAM(500, 250, 250),
				),
			},
			RataMinRAM: 300,
			ExpectedDestroyHypervisor: &operationsv1.DestroyHypervisorsRequest{
				Ids: []string{"2"},
			},
		},
		"if there aren't enough ram, but there's a small hyper in the dead row and with it the system can work, remove it from the dead row": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("1"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(true),
					testhelper.WithDestroyTime(time.Now().Add(2*director.DeadRowDuration)),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithRAM(600, 400, 200),
				),
				testhelper.Hypervisor(
					testhelper.WithID("2"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithDesktopsStarted(0),
					testhelper.WithOnlyForced(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithRAM(700, 100, 600),
				),
			},
			RataMinRAM:            700,
			ExpectedRemoveDeadRow: []string{"1"},
		},
		"regression test #1": {
			AvailHypers: []*operationsv1.ListHypervisorsResponseHypervisor{},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("bm-e4-01"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(10),
					testhelper.WithMinFreeMemGB(190),
					testhelper.WithRAM(2051961, 67556, 1984404),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e2-02"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithDesktopsStarted(2),
					testhelper.WithOnlyForced(false),
					testhelper.WithOrchestratorManaged(false),
					testhelper.WithMinFreeMemGB(47),
					testhelper.WithRAM(515855, 65620, 450234),
				),
			},
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
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("bm-e4-04"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(46),
					testhelper.WithMinFreeMemGB(180),
					testhelper.WithRAM(2051975, 232253, 1819722),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e2-02"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithDesktopsStarted(18),
					testhelper.WithOnlyForced(false),
					testhelper.WithOrchestratorManaged(false),
					testhelper.WithMinFreeMemGB(47),
					testhelper.WithRAM(515855, 125714, 390140),
				),
			},
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
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("bm-e4-01"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithDestroyTime(time.Time{}),
					testhelper.WithBookingsEndTime(time.Time{}),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithGpuOnly(false),
					testhelper.WithDesktopsStarted(57),
					testhelper.WithMinFreeMemGB(190),
					testhelper.WithCPU(100, 6, 94),
					testhelper.WithRAM(2051961, 305801, 1746160),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e2-02"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithDestroyTime(time.Time{}),
					testhelper.WithBookingsEndTime(time.Time{}),
					testhelper.WithOrchestratorManaged(false),
					testhelper.WithGpuOnly(false),
					testhelper.WithDesktopsStarted(23),
					testhelper.WithMinFreeMemGB(47),
					testhelper.WithCPU(100, 7, 93),
					testhelper.WithRAM(515855, 160998, 354856),
				),
			},
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
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("1"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithRAM(500, 400, 100),
				),
				testhelper.Hypervisor(
					testhelper.WithID("2"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithDestroyTime(time.Time{}),
					testhelper.WithDesktopsStarted(0),
					testhelper.WithOnlyForced(true),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithRAM(700, 100, 600),
				),
			},
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
			Hypers:     []*model.Hypervisor{},
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
		Hypers      []*model.Hypervisor
		HyperMinCPU int
		HyperMinRAM int
		HyperMaxRAM int
		ExpectedErr string
	}{
		"if there are enough resources, it shouldn't do anything": {
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("first"),
					testhelper.WithStatus(model.HypervisorStatusOffline),
					testhelper.WithRAM(0, 0, 10),
				),
				testhelper.Hypervisor(
					testhelper.WithID("second"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithRAM(0, 0, 60),
				),
			},
			HyperMinRAM: 50,
		},
		"if there's not enough RAM, it should set the hypervisor to only forced": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.Mock.On("AdminTableUpdate", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req apiv4.AdminTableUpdateReq) bool {
					return string(req["id"]) == `"second"` && string(req["only_forced"]) == "true"
				}), apiv4.AdminTableUpdateParams{Table: "hypervisors"}).Return(&apiv4.AdminTableUpdateNoContent{}, nil)
			},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("first"),
					testhelper.WithStatus(model.HypervisorStatusOffline),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithRAM(0, 0, 10),
				),
				testhelper.Hypervisor(
					testhelper.WithID("second"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithRAM(0, 0, 30),
				),
			},
			HyperMinRAM: 50,
		},
		"if there's too much free RAM, it should remove the hypervisor from only forced": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.Mock.On("AdminTableUpdate", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req apiv4.AdminTableUpdateReq) bool {
					return string(req["id"]) == `"second"` && string(req["only_forced"]) == "false"
				}), apiv4.AdminTableUpdateParams{Table: "hypervisors"}).Return(&apiv4.AdminTableUpdateNoContent{}, nil)
			},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("first"),
					testhelper.WithStatus(model.HypervisorStatusOffline),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(1312),
					testhelper.WithRAM(0, 0, 10),
				),
				testhelper.Hypervisor(
					testhelper.WithID("second"),
					testhelper.WithOnlyForced(true),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(1312),
					testhelper.WithRAM(0, 0, 200),
				),
			},
			HyperMinRAM: 30,
			HyperMaxRAM: 150,
		},
		"regresssion test #1": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.Mock.On("AdminTableUpdate", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req apiv4.AdminTableUpdateReq) bool {
					return string(req["id"]) == `"bm-e2-03"` && string(req["only_forced"]) == "true"
				}), apiv4.AdminTableUpdateParams{Table: "hypervisors"}).Return(&apiv4.AdminTableUpdateNoContent{}, nil)
				c.Mock.On("AdminTableUpdate", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req apiv4.AdminTableUpdateReq) bool {
					return string(req["id"]) == `"bm-e2-01"` && string(req["only_forced"]) == "true"
				}), apiv4.AdminTableUpdateParams{Table: "hypervisors"}).Return(&apiv4.AdminTableUpdateNoContent{}, nil)
			},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("bm-e4-02"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(39),
					testhelper.WithMinFreeMemGB(190),
					testhelper.WithCPU(100, 7, 93),
					testhelper.WithRAM(2051961, 249909, 1802051),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e4-01"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithDestroyTime(time.Now()),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(266),
					testhelper.WithMinFreeMemGB(190),
					testhelper.WithCPU(100, 23, 77),
					testhelper.WithRAM(2051961, 1540080, 511881),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e2-03"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(70),
					testhelper.WithMinFreeMemGB(47),
					testhelper.WithCPU(100, 30, 70),
					testhelper.WithRAM(515855, 407554, 108300),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e2-01"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(77),
					testhelper.WithMinFreeMemGB(47),
					testhelper.WithCPU(100, 27, 73),
					testhelper.WithRAM(515855, 409618, 106237),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e2-02"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithOrchestratorManaged(false),
					testhelper.WithDesktopsStarted(64),
					testhelper.WithMinFreeMemGB(47),
					testhelper.WithCPU(100, 25, 75),
					testhelper.WithRAM(515855, 441597, 74258),
				),
			},
			HyperMinRAM: 92160,
			HyperMaxRAM: 153600,
		},
		"regression test #2": {
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("bm-e4-02"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(39),
					testhelper.WithMinFreeMemGB(190),
					testhelper.WithCPU(100, 7, 93),
					testhelper.WithRAM(2051961, 249909, 1802051),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e4-01"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithDestroyTime(time.Now()),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(266),
					testhelper.WithMinFreeMemGB(190),
					testhelper.WithCPU(100, 23, 77),
					testhelper.WithRAM(2051961, 1540080, 511881),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e2-03"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(true),
					testhelper.WithBuffering(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(70),
					testhelper.WithMinFreeMemGB(47),
					testhelper.WithCPU(100, 30, 70),
					testhelper.WithRAM(515855, 407554, 108300),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e2-01"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(true),
					testhelper.WithBuffering(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(77),
					testhelper.WithMinFreeMemGB(47),
					testhelper.WithCPU(100, 27, 73),
					testhelper.WithRAM(515855, 409618, 106237),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e2-02"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithOrchestratorManaged(false),
					testhelper.WithDesktopsStarted(64),
					testhelper.WithMinFreeMemGB(47),
					testhelper.WithCPU(100, 25, 75),
					testhelper.WithRAM(515855, 441597, 74258),
				),
			},
			HyperMinRAM: 92160,
			HyperMaxRAM: 153600,
		},
		"should not remove an hypervisor from only forced if it has no desktops (will be removed by NeedsToScaleHypervisors)": {
			PrepareAPI: func(*apiv4.MockInvoker) {},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("gpu-a10-01"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithDestroyTime(time.Time{}),
					testhelper.WithBookingsEndTime(time.Time{}),
					testhelper.WithOrchestratorManaged(false),
					testhelper.WithGpuOnly(false),
					testhelper.WithDesktopsStarted(60),
					testhelper.WithMinFreeMemGB(100),
					testhelper.WithCPU(100, 17, 83),
					testhelper.WithRAM(1031694, 519912, 511782),
					testhelper.WithGPUs([]apiv4.OrchestratorHypervisorGPU{{
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
					}}),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e2-11"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(true),
					testhelper.WithBuffering(false),
					testhelper.WithDestroyTime(time.Time{}),
					testhelper.WithBookingsEndTime(time.Time{}),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithGpuOnly(false),
					testhelper.WithDesktopsStarted(0),
					testhelper.WithMinFreeMemGB(50),
					testhelper.WithCPU(100, 2, 98),
					testhelper.WithRAM(515850, 3538, 512311),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e2-12"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithDestroyTime(time.Time{}),
					testhelper.WithBookingsEndTime(time.Time{}),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithGpuOnly(false),
					testhelper.WithDesktopsStarted(55),
					testhelper.WithMinFreeMemGB(50),
					testhelper.WithCPU(100, 18, 81),
					testhelper.WithRAM(515849, 335477, 180372),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e4-12"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithBuffering(false),
					testhelper.WithDestroyTime(time.Time{}),
					testhelper.WithBookingsEndTime(time.Time{}),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithGpuOnly(false),
					testhelper.WithDesktopsStarted(202),
					testhelper.WithMinFreeMemGB(200),
					testhelper.WithCPU(100, 14, 86),
					testhelper.WithRAM(2051891, 1300091, 751799),
				),
				testhelper.Hypervisor(
					testhelper.WithID("bm-e4-16"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(true),
					testhelper.WithBuffering(false),
					testhelper.WithDestroyTime(time.Now()),
					testhelper.WithBookingsEndTime(time.Time{}),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithGpuOnly(false),
					testhelper.WithDesktopsStarted(156),
					testhelper.WithMinFreeMemGB(200),
					testhelper.WithCPU(100, 11, 89),
					testhelper.WithRAM(2051891, 1118939, 932951),
				),
				testhelper.Hypervisor(
					testhelper.WithID("e4-21"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(true),
					testhelper.WithBuffering(false),
					testhelper.WithDestroyTime(time.Now()),
					testhelper.WithBookingsEndTime(time.Time{}),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithGpuOnly(false),
					testhelper.WithDesktopsStarted(240),
					testhelper.WithMinFreeMemGB(200),
					testhelper.WithCPU(100, 17, 83),
					testhelper.WithRAM(2051891, 1466408, 585482),
				),
			},
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
