package director

import (
	"os"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/model"
	"gitlab.com/isard/isardvdi/orchestrator/orchestrator/model/testhelper"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
)

func TestMinRAM(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		Hypers                   []*model.Hypervisor
		MinRAM                   int
		MinRAMHourly             map[time.Weekday]map[time.Time]int
		MinRAMLimitPercent       int
		MinRAMLimitPercentHourly map[time.Weekday]map[time.Time]int
		MinRAMLimitMargin        int
		MinRAMLimitMarginHourly  map[time.Weekday]map[time.Time]int
		HyperMinRAM              int
		HyperMaxRAM              int
		Expected                 int
	}{
		"should return 0 if it's not configured": {
			Expected: 0,
		},
		"should get the min ram correctly": {
			MinRAM:   3,
			Expected: 3,
		},
		"should get the hourly limit correctly": {
			MinRAMHourly: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(1, 1, 1, 0, 0, 0, 0, time.UTC): 25,
				},
			},
			Expected: 25,
		},
		"should apply the percentage correctly using a fixed margin": {
			MinRAMLimitPercent: 200,
			MinRAMLimitMargin:  300,
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("1"), testhelper.WithMinFreeMemGB(2)),
				testhelper.Hypervisor(testhelper.WithID("2"), testhelper.WithMinFreeMemGB(5)),
			},
			Expected: 5*1024*2 + 2*1024*2 + 300,
		},
		"should apply the percentage correctly using a hourly margin": {
			MinRAMLimitPercent: 150,
			MinRAMLimitMarginHourly: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(1, 1, 1, 0, 0, 0, 0, time.UTC): 1312,
				},
			},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("1"), testhelper.WithMinFreeMemGB(3)),
				testhelper.Hypervisor(testhelper.WithID("2"), testhelper.WithMinFreeMemGB(2)),
			},
			Expected: (3*1024)*1.5 + (2*1024)*1.5 + 1312,
		},
		"regression test #1": {
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
			MinRAMLimitPercent: 150,
			MinRAMLimitMargin:  1,
			HyperMinRAM:        51200,
			HyperMaxRAM:        102400,

			Expected: ((47*1024 + 51200) * 1.5) + ((190*1024 + 51200) * 1.5) + 1,
		},
		"regression test #2": {
			Hypers: []*model.Hypervisor{
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
			MinRAMLimitPercent: 150,
			MinRAMLimitMargin:  1,
			HyperMinRAM:        51200,
			HyperMaxRAM:        102400,

			Expected: ((47*1024 + 51200) * 1.5) + 1,
		},
		"should get the limit percent hourly if configured": {
			MinRAMLimitPercentHourly: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(1, 1, 1, 0, 0, 0, 0, time.UTC): 150,
				},
			},
			MinRAMLimitMarginHourly: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(1, 1, 1, 0, 0, 0, 0, time.UTC): 1312,
				},
			},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("1"), testhelper.WithMinFreeMemGB(3)),
				testhelper.Hypervisor(testhelper.WithID("2"), testhelper.WithMinFreeMemGB(2)),
			},
			Expected: (3*1024)*1.5 + (2*1024)*1.5 + 1312,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{
				MinRAM:                   tc.MinRAM,
				MinRAMHourly:             tc.MinRAMHourly,
				MinRAMLimitPercent:       tc.MinRAMLimitPercent,
				MinRAMLimitPercentHourly: tc.MinRAMLimitPercentHourly,
				MinRAMLimitMargin:        tc.MinRAMLimitMargin,
				MinRAMLimitMarginHourly:  tc.MinRAMLimitMarginHourly,
				HyperMinRAM:              tc.HyperMinRAM,
				HyperMaxRAM:              tc.HyperMaxRAM,
			}, false, &log, nil)

			assert.Equal(tc.Expected, rata.minRAM(tc.Hypers))
		})
	}
}

func TestMaxRAM(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		Hypers                   []*model.Hypervisor
		MaxRAM                   int
		MaxRAMHourly             map[time.Weekday]map[time.Time]int
		MaxRAMLimitPercent       int
		MaxRAMLimitPercentHourly map[time.Weekday]map[time.Time]int
		MaxRAMLimitMargin        int
		MaxRAMLimitMarginHourly  map[time.Weekday]map[time.Time]int
		Expected                 int
	}{
		"should return 0 if it's not configured": {
			Expected: 0,
		},
		"should get the max ram correctly": {
			MaxRAM:   3,
			Expected: 3,
		},
		"should get the hourly limit correctly": {
			MaxRAMHourly: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(1, 1, 1, 0, 0, 0, 0, time.UTC): 25,
				},
			},
			Expected: 25,
		},
		"should apply the percentage correctly using a fixed margin": {
			MaxRAMLimitPercent: 200,
			MaxRAMLimitMargin:  300,
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("1"), testhelper.WithMinFreeMemGB(2)),
				testhelper.Hypervisor(testhelper.WithID("2"), testhelper.WithMinFreeMemGB(5)),
			},
			Expected: 5*1024*2 + 2*1024*2 + 300,
		},
		"should apply the percentage correctly using a hourly margin": {
			MaxRAMLimitPercent: 150,
			MaxRAMLimitMarginHourly: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(1, 1, 1, 0, 0, 0, 0, time.UTC): 1312,
				},
			},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("1"), testhelper.WithMinFreeMemGB(3)),
				testhelper.Hypervisor(testhelper.WithID("2"), testhelper.WithMinFreeMemGB(2)),
			},
			Expected: (3*1024)*1.5 + (2*1024)*1.5 + 1312,
		},
		"should get the limit percent hourly if configured": {
			MaxRAMLimitPercentHourly: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(1, 1, 1, 0, 0, 0, 0, time.UTC): 150,
				},
			},
			MaxRAMLimitMarginHourly: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(1, 1, 1, 0, 0, 0, 0, time.UTC): 1312,
				},
			},
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("1"), testhelper.WithMinFreeMemGB(3)),
				testhelper.Hypervisor(testhelper.WithID("2"), testhelper.WithMinFreeMemGB(2)),
			},
			Expected: (3*1024)*1.5 + (2*1024)*1.5 + 1312,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{
				MaxRAM:                   tc.MaxRAM,
				MaxRAMHourly:             tc.MaxRAMHourly,
				MaxRAMLimitPercent:       tc.MaxRAMLimitPercent,
				MaxRAMLimitPercentHourly: tc.MaxRAMLimitPercentHourly,
				MaxRAMLimitMargin:        tc.MaxRAMLimitMargin,
				MaxRAMLimitMarginHourly:  tc.MaxRAMLimitMarginHourly,
			}, false, &log, nil)

			assert.Equal(tc.Expected, rata.maxRAM(tc.Hypers))
		})
	}
}

func TestClassifyHypervisors(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		Hypers                []*model.Hypervisor
		ExpectedToAcknowledge []*model.Hypervisor
		ExpectedToHandle      []*model.Hypervisor
		ExpectedOnDeadRow     []*model.Hypervisor
		ExpectedLimited       []*model.Hypervisor
	}{
		"should classify the hypervisors correctly": {
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("hyper1"), testhelper.WithStatus(model.HypervisorStatusOnline)),
				testhelper.Hypervisor(testhelper.WithID("hyper2"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOrchestratorManaged(true)),
				testhelper.Hypervisor(testhelper.WithID("hyper3"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOrchestratorManaged(true), testhelper.WithOnlyForced(true), testhelper.WithDestroyTime(time.Date(1, 2, 3, 4, 5, 6, 7, time.UTC))),
				testhelper.Hypervisor(testhelper.WithID("hyper4"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOrchestratorManaged(true), testhelper.WithOnlyForced(true)),
			},
			ExpectedToAcknowledge: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("hyper1"), testhelper.WithStatus(model.HypervisorStatusOnline)),
				testhelper.Hypervisor(testhelper.WithID("hyper2"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOrchestratorManaged(true)),
			},
			ExpectedToHandle: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("hyper2"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOrchestratorManaged(true)),
				testhelper.Hypervisor(testhelper.WithID("hyper3"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOrchestratorManaged(true), testhelper.WithOnlyForced(true), testhelper.WithDestroyTime(time.Date(1, 2, 3, 4, 5, 6, 7, time.UTC))),
				testhelper.Hypervisor(testhelper.WithID("hyper4"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOrchestratorManaged(true), testhelper.WithOnlyForced(true)),
			},
			ExpectedOnDeadRow: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("hyper3"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOrchestratorManaged(true), testhelper.WithOnlyForced(true), testhelper.WithDestroyTime(time.Date(1, 2, 3, 4, 5, 6, 7, time.UTC))),
			},
			ExpectedLimited: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("hyper4"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOrchestratorManaged(true), testhelper.WithOnlyForced(true)),
			},
		},
		"should ignore the offline hypervisors": {
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("offline"), testhelper.WithStatus(model.HypervisorStatusOffline)),
			},
			ExpectedToAcknowledge: []*model.Hypervisor{},
			ExpectedToHandle:      []*model.Hypervisor{},
			ExpectedOnDeadRow:     []*model.Hypervisor{},
			ExpectedLimited:       []*model.Hypervisor{},
		},
		"should ignore buffering hypervisors": {
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("buffering"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithBuffering(true)),
			},
			ExpectedToAcknowledge: []*model.Hypervisor{},
			ExpectedToHandle:      []*model.Hypervisor{},
			ExpectedOnDeadRow:     []*model.Hypervisor{},
			ExpectedLimited:       []*model.Hypervisor{},
		},
		"should ignore GPU only hypervisors": {
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("gpu only"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithGpuOnly(true)),
			},
			ExpectedToAcknowledge: []*model.Hypervisor{},
			ExpectedToHandle:      []*model.Hypervisor{},
			ExpectedOnDeadRow:     []*model.Hypervisor{},
			ExpectedLimited:       []*model.Hypervisor{},
		},
		"should not add only forced hypervisors to the acknowledge list": {
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("only forced"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOnlyForced(true)),
			},
			ExpectedToAcknowledge: []*model.Hypervisor{},
			ExpectedToHandle:      []*model.Hypervisor{},
			ExpectedOnDeadRow:     []*model.Hypervisor{},
			ExpectedLimited:       []*model.Hypervisor{},
		},
		"should not add a non orchestrator managed hypervisor to the handle list": {
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("unmanaged"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOrchestratorManaged(false)),
			},
			ExpectedToAcknowledge: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("unmanaged"), testhelper.WithStatus(model.HypervisorStatusOnline), testhelper.WithOrchestratorManaged(false)),
			},
			ExpectedToHandle:  []*model.Hypervisor{},
			ExpectedOnDeadRow: []*model.Hypervisor{},
			ExpectedLimited:   []*model.Hypervisor{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{}, false, &log, nil)

			hypersToAcknowledge, hypersToHandle, hypersOnDeadRow, hypersLimited := rata.classifyHypervisors(tc.Hypers)

			assert.Equal(tc.ExpectedToAcknowledge, hypersToAcknowledge)
			assert.Equal(tc.ExpectedToHandle, hypersToHandle)
			assert.Equal(tc.ExpectedOnDeadRow, hypersOnDeadRow)
			assert.Equal(tc.ExpectedLimited, hypersLimited)
		})
	}
}

func TestBestHyperToCreate(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		Hypers      []*operationsv1.ListHypervisorsResponseHypervisor
		MinCPU      int
		MinRAM      int
		Expected    string
		ExpectedErr string
	}{
		"should work as expected": {
			Hypers: []*operationsv1.ListHypervisorsResponseHypervisor{
				{
					Id:    "smol :3 unavailable",
					State: operationsv1.HypervisorState_HYPERVISOR_STATE_UNKNOWN,
					Ram:   2,
				},
				{
					Id:    "GIGANTIC",
					State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
					Ram:   9999,
				},
				{
					Id:    "correct",
					State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
					Ram:   3,
				},
			},
			MinRAM:   1,
			Expected: "correct",
		},
		"should return the biggest hypervisor if there's no hypervisor big enough for the requirements": {
			Hypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:    "smol :3",
				Ram:   1,
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
			}, {
				Id:    "medium",
				Ram:   2,
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
			}, {
				Id:    "correct",
				Ram:   3,
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
			}},
			MinRAM:   4,
			Expected: "correct",
		},
		"should return an error if there's no suitable hypervisor": {
			Hypers:      []*operationsv1.ListHypervisorsResponseHypervisor{},
			MinRAM:      2,
			ExpectedErr: "no hypervisor with the required resources and capabilities available",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{}, false, &log, nil)

			id, err := rata.bestHyperToCreate(tc.Hypers, tc.MinCPU, tc.MinRAM)

			assert.Equal(tc.Expected, id)
			if tc.ExpectedErr == "" {
				assert.NoError(err)
			} else {
				assert.EqualError(err, tc.ExpectedErr)
			}
		})
	}
}

func TestBestHyperToPardon(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		DeadRow  []*model.Hypervisor
		RAMAvail int
		MinCPU   int
		MinRAM   int
		Expected *model.Hypervisor
	}{
		"should return the hypervisor that has the longest dead row sentence": {
			DeadRow: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("smol :3"), testhelper.WithDestroyTime(time.Date(9999, 1, 1, 1, 1, 1, 1, time.UTC))),
				testhelper.Hypervisor(testhelper.WithID("life sentence"), testhelper.WithDestroyTime(time.Date(8888, 1, 1, 1, 1, 1, 1, time.UTC)), testhelper.WithRAM(9999, 0, 999)),
				testhelper.Hypervisor(testhelper.WithID("short sentence"), testhelper.WithDestroyTime(time.Now()), testhelper.WithRAM(10, 0, 9)),
			},
			MinRAM:   2,
			RAMAvail: 1,
			Expected: testhelper.Hypervisor(testhelper.WithID("life sentence"), testhelper.WithDestroyTime(time.Date(8888, 1, 1, 1, 1, 1, 1, time.UTC)), testhelper.WithRAM(9999, 0, 999)),
		},
		"should ensure that the hypervisor meets the minimum RAM requirements": {
			DeadRow: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("smol :3")),
			},
			MinRAM:   1,
			Expected: nil,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{}, false, &log, nil)

			assert.Equal(tc.Expected, rata.bestHyperToPardon(tc.DeadRow, tc.RAMAvail, tc.MinCPU, tc.MinRAM))
		})
	}
}

func TestBestHyperToDestroy(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	now := time.Now()

	cases := map[string]struct {
		Hypers   []*model.Hypervisor
		Expected *model.Hypervisor
	}{
		"should work correctly": {
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("not to destroy"), testhelper.WithOnlyForced(true)),
				testhelper.Hypervisor(testhelper.WithID("to destroy"), testhelper.WithOnlyForced(true), testhelper.WithDesktopsStarted(1000), testhelper.WithDestroyTime(now.Add(-1*time.Hour))),
			},
			Expected: testhelper.Hypervisor(testhelper.WithID("to destroy"), testhelper.WithOnlyForced(true), testhelper.WithDesktopsStarted(1000), testhelper.WithDestroyTime(now.Add(-1*time.Hour))),
		},
		"should remove a desktop with a destroy time and 0 desktops": {
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("not to destroy"), testhelper.WithOnlyForced(true)),
				testhelper.Hypervisor(testhelper.WithID("to destroy"), testhelper.WithOnlyForced(true), testhelper.WithDesktopsStarted(0), testhelper.WithDestroyTime(now.Add(1*time.Hour))),
			},
			Expected: testhelper.Hypervisor(testhelper.WithID("to destroy"), testhelper.WithOnlyForced(true), testhelper.WithDesktopsStarted(0), testhelper.WithDestroyTime(now.Add(1*time.Hour))),
		},
		"should avoid killing hypervisors that aren't in only forced, due a mismanagement": {
			Hypers: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("not to destroy"), testhelper.WithOnlyForced(false), testhelper.WithDesktopsStarted(1000), testhelper.WithDestroyTime(now.Add(-1*time.Hour))),
			},
			Expected: nil,
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{}, false, &log, nil)

			assert.Equal(tc.Expected, rata.bestHyperToDestroy(tc.Hypers))
		})
	}
}

func TestBestHyperToMoveInDeadRow(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		HypersToAcknowledge []*model.Hypervisor
		HypersToManage      []*model.Hypervisor
		RAMAvail            int
		MinRAM              int
		MaxRAM              int
		MinRAMLimitPercent  int
		MinRAMLimitMargin   int
		MaxRAMLimitPercent  int
		MaxRAMLimitMargin   int
		Expected            *model.Hypervisor
	}{
		"should work correctly": {
			HypersToAcknowledge: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("smol :3"), testhelper.WithRAM(1, 0, 1)),
				testhelper.Hypervisor(testhelper.WithID("to sentence"), testhelper.WithRAM(2, 0, 2)),
				testhelper.Hypervisor(testhelper.WithID("GIGANTIC"), testhelper.WithRAM(10, 0, 10)),
			},
			HypersToManage: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("smol :3"), testhelper.WithRAM(1, 0, 1)),
				testhelper.Hypervisor(testhelper.WithID("to sentence"), testhelper.WithRAM(2, 0, 2)),
				testhelper.Hypervisor(testhelper.WithID("GIGANTIC"), testhelper.WithRAM(10, 0, 10)),
			},
			MinRAM:   10,
			MaxRAM:   12,
			RAMAvail: 13,
			Expected: testhelper.Hypervisor(testhelper.WithID("to sentence"), testhelper.WithRAM(2, 0, 2)),
		},
		"should work correctly with only forced hypevisors": {
			HypersToAcknowledge: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("smol :3"), testhelper.WithRAM(1, 0, 1)),
				testhelper.Hypervisor(testhelper.WithID("normal"), testhelper.WithRAM(2, 0, 2)),
				testhelper.Hypervisor(testhelper.WithID("GIGANTIC"), testhelper.WithOnlyForced(true), testhelper.WithRAM(10, 0, 10)),
			},
			HypersToManage: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("smol :3"), testhelper.WithRAM(1, 0, 1)),
				testhelper.Hypervisor(testhelper.WithID("normal"), testhelper.WithRAM(2, 0, 2)),
				testhelper.Hypervisor(testhelper.WithID("GIGANTIC"), testhelper.WithOnlyForced(true), testhelper.WithRAM(10, 0, 10)),
			},
			MinRAM:   1,
			MaxRAM:   2,
			RAMAvail: 3,
			Expected: testhelper.Hypervisor(testhelper.WithID("GIGANTIC"), testhelper.WithOnlyForced(true), testhelper.WithRAM(10, 0, 10)),
		},
		"should not return any hypervisor if by removing it we don't meet the minRAM requirement": {
			HypersToAcknowledge: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("smol :3"), testhelper.WithRAM(1, 0, 1)),
				testhelper.Hypervisor(testhelper.WithID("can't sentence"), testhelper.WithRAM(2, 0, 2)),
			},
			HypersToManage: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("smol :3"), testhelper.WithRAM(1, 0, 1)),
				testhelper.Hypervisor(testhelper.WithID("can't sentence"), testhelper.WithRAM(2, 0, 2)),
			},
			MinRAM:   3,
			MaxRAM:   2,
			RAMAvail: 3,
		},
		"should ignore hypervisors already in the dead row": {
			HypersToAcknowledge: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("smol :3"), testhelper.WithRAM(1, 0, 1)),
				testhelper.Hypervisor(testhelper.WithID("to ignore"), testhelper.WithDestroyTime(time.Now()), testhelper.WithRAM(2, 0, 2)),
			},
			HypersToManage: []*model.Hypervisor{
				testhelper.Hypervisor(testhelper.WithID("smol :3"), testhelper.WithRAM(1, 0, 1)),
				testhelper.Hypervisor(testhelper.WithID("to ignore"), testhelper.WithDestroyTime(time.Now()), testhelper.WithRAM(2, 0, 2)),
			},
			MinRAM:   1,
			MaxRAM:   1,
			RAMAvail: 1,
		},
		"regression test #1": {
			HypersToAcknowledge: []*model.Hypervisor{
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
			HypersToManage: []*model.Hypervisor{
				testhelper.Hypervisor(
					testhelper.WithID("bm-e4-01"),
					testhelper.WithStatus(model.HypervisorStatusOnline),
					testhelper.WithOnlyForced(false),
					testhelper.WithOrchestratorManaged(true),
					testhelper.WithDesktopsStarted(10),
					testhelper.WithMinFreeMemGB(190),
					testhelper.WithRAM(2051961, 67556, 1984404),
				),
			},
			RAMAvail:           2191950,
			MinRAMLimitPercent: 150,
			MinRAMLimitMargin:  1,
			MaxRAMLimitPercent: 150,
			MaxRAMLimitMargin:  112640,
			Expected: testhelper.Hypervisor(
				testhelper.WithID("bm-e4-01"),
				testhelper.WithStatus(model.HypervisorStatusOnline),
				testhelper.WithOnlyForced(false),
				testhelper.WithOrchestratorManaged(true),
				testhelper.WithDesktopsStarted(10),
				testhelper.WithMinFreeMemGB(190),
				testhelper.WithRAM(2051961, 67556, 1984404),
			),
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{
				MinRAM:             tc.MinRAM,
				MaxRAM:             tc.MaxRAM,
				MinRAMLimitPercent: tc.MinRAMLimitPercent,
				MinRAMLimitMargin:  tc.MinRAMLimitMargin,
				MaxRAMLimitPercent: tc.MaxRAMLimitPercent,
				MaxRAMLimitMargin:  tc.MaxRAMLimitMargin,
			}, false, &log, nil)

			assert.Equal(tc.Expected, rata.bestHyperToMoveInDeadRow(tc.HypersToAcknowledge, tc.HypersToManage, tc.RAMAvail))
		})
	}
}
