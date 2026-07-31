package director

import (
	"os"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
)

func TestMinRAM(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		Hypers                   []*apiv4.OrchestratorHypervisor
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
			Hypers: []*apiv4.OrchestratorHypervisor{
				{
					ID:           "1",
					MinFreeMemGB: 2,
				},
				{
					ID:           "2",
					MinFreeMemGB: 5,
				},
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
			Hypers: []*apiv4.OrchestratorHypervisor{
				{
					ID:           "1",
					MinFreeMemGB: 3,
				},
				{
					ID:           "2",
					MinFreeMemGB: 2,
				},
			},
			Expected: (3*1024)*1.5 + (2*1024)*1.5 + 1312,
		},
		"regression test #1": {
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
			MinRAMLimitPercent: 150,
			MinRAMLimitMargin:  1,
			HyperMinRAM:        51200,
			HyperMaxRAM:        102400,

			Expected: ((47*1024 + 51200) * 1.5) + ((190*1024 + 51200) * 1.5) + 1,
		},
		"regression test #2": {
			Hypers: []*apiv4.OrchestratorHypervisor{{
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
			Hypers: []*apiv4.OrchestratorHypervisor{
				{
					ID:           "1",
					MinFreeMemGB: 3,
				},
				{
					ID:           "2",
					MinFreeMemGB: 2,
				},
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
		Hypers                   []*apiv4.OrchestratorHypervisor
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
			Hypers: []*apiv4.OrchestratorHypervisor{
				{
					ID:           "1",
					MinFreeMemGB: 2,
				},
				{
					ID:           "2",
					MinFreeMemGB: 5,
				},
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
			Hypers: []*apiv4.OrchestratorHypervisor{
				{
					ID:           "1",
					MinFreeMemGB: 3,
				},
				{
					ID:           "2",
					MinFreeMemGB: 2,
				},
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
			Hypers: []*apiv4.OrchestratorHypervisor{
				{
					ID:           "1",
					MinFreeMemGB: 3,
				},
				{
					ID:           "2",
					MinFreeMemGB: 2,
				},
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
		Hypers                []*apiv4.OrchestratorHypervisor
		ExpectedToAcknowledge []*apiv4.OrchestratorHypervisor
		ExpectedToHandle      []*apiv4.OrchestratorHypervisor
		ExpectedOnDeadRow     []*apiv4.OrchestratorHypervisor
		ExpectedLimited       []*apiv4.OrchestratorHypervisor
	}{
		"should classify the hypervisors correctly": {
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:     "hyper1",
				Status: apiv4.HypervisorStatusOnline,
			}, {
				ID:                  "hyper2",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: true,
			}, {
				ID:                  "hyper3",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: true,
				OnlyForced:          true,
				DestroyTime:         apiv4.NewNilDateTime(time.Date(1, 2, 3, 4, 5, 6, 7, time.UTC)),
			}, {
				ID:                  "hyper4",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: true,
				OnlyForced:          true,
			}},
			ExpectedToAcknowledge: []*apiv4.OrchestratorHypervisor{{
				ID:     "hyper1",
				Status: apiv4.HypervisorStatusOnline,
			}, {
				ID:                  "hyper2",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: true,
			}},
			ExpectedToHandle: []*apiv4.OrchestratorHypervisor{{
				ID:                  "hyper2",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: true,
			}, {
				ID:                  "hyper3",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: true,
				OnlyForced:          true,
				DestroyTime:         apiv4.NewNilDateTime(time.Date(1, 2, 3, 4, 5, 6, 7, time.UTC)),
			}, {
				ID:                  "hyper4",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: true,
				OnlyForced:          true,
			}},
			ExpectedOnDeadRow: []*apiv4.OrchestratorHypervisor{{
				ID:                  "hyper3",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: true,
				OnlyForced:          true,
				DestroyTime:         apiv4.NewNilDateTime(time.Date(1, 2, 3, 4, 5, 6, 7, time.UTC)),
			}},
			ExpectedLimited: []*apiv4.OrchestratorHypervisor{{
				ID:                  "hyper4",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: true,
				OnlyForced:          true,
			}},
		},
		"should ignore the offline hypervisors": {
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:     "offline",
				Status: apiv4.HypervisorStatusOffline,
			}},
			ExpectedToAcknowledge: []*apiv4.OrchestratorHypervisor{},
			ExpectedToHandle:      []*apiv4.OrchestratorHypervisor{},
			ExpectedOnDeadRow:     []*apiv4.OrchestratorHypervisor{},
			ExpectedLimited:       []*apiv4.OrchestratorHypervisor{},
		},
		"should ignore buffering hypervisors": {
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:             "buffering",
				Status:         apiv4.HypervisorStatusOnline,
				BufferingHyper: true,
			}},
			ExpectedToAcknowledge: []*apiv4.OrchestratorHypervisor{},
			ExpectedToHandle:      []*apiv4.OrchestratorHypervisor{},
			ExpectedOnDeadRow:     []*apiv4.OrchestratorHypervisor{},
			ExpectedLimited:       []*apiv4.OrchestratorHypervisor{},
		},
		"should ignore GPU only hypervisors": {
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:      "gpu only",
				Status:  apiv4.HypervisorStatusOnline,
				GpuOnly: true,
			}},
			ExpectedToAcknowledge: []*apiv4.OrchestratorHypervisor{},
			ExpectedToHandle:      []*apiv4.OrchestratorHypervisor{},
			ExpectedOnDeadRow:     []*apiv4.OrchestratorHypervisor{},
			ExpectedLimited:       []*apiv4.OrchestratorHypervisor{},
		},
		"should not add only forced hypervisors to the acknowledge list": {
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:         "only forced",
				Status:     apiv4.HypervisorStatusOnline,
				OnlyForced: true,
			}},
			ExpectedToAcknowledge: []*apiv4.OrchestratorHypervisor{},
			ExpectedToHandle:      []*apiv4.OrchestratorHypervisor{},
			ExpectedOnDeadRow:     []*apiv4.OrchestratorHypervisor{},
			ExpectedLimited:       []*apiv4.OrchestratorHypervisor{},
		},
		"should not add a non orchestrator managed hypervisor to the handle list": {
			Hypers: []*apiv4.OrchestratorHypervisor{{
				ID:                  "unmanaged",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: false,
			}},
			ExpectedToAcknowledge: []*apiv4.OrchestratorHypervisor{{
				ID:                  "unmanaged",
				Status:              apiv4.HypervisorStatusOnline,
				OrchestratorManaged: false,
			}},
			ExpectedToHandle:  []*apiv4.OrchestratorHypervisor{},
			ExpectedOnDeadRow: []*apiv4.OrchestratorHypervisor{},
			ExpectedLimited:   []*apiv4.OrchestratorHypervisor{},
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
		DeadRow  []*apiv4.OrchestratorHypervisor
		RAMAvail int
		MinCPU   int
		MinRAM   int
		Expected *apiv4.OrchestratorHypervisor
	}{
		"should return the hypervisor that has the longest dead row sentence": {
			DeadRow: []*apiv4.OrchestratorHypervisor{{
				ID:          "smol :3",
				DestroyTime: apiv4.NewNilDateTime(time.Date(9999, 1, 1, 1, 1, 1, 1, time.UTC)),
			}, {
				ID:          "life sentence",
				DestroyTime: apiv4.NewNilDateTime(time.Date(8888, 1, 1, 1, 1, 1, 1, time.UTC)),
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 9999,
					Free:  999,
				},
			}, {
				ID:          "short sentence",
				DestroyTime: apiv4.NewNilDateTime(time.Now()),
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 10,
					Free:  9,
				},
			}},
			MinRAM:   2,
			RAMAvail: 1,
			Expected: &apiv4.OrchestratorHypervisor{
				ID:          "life sentence",
				DestroyTime: apiv4.NewNilDateTime(time.Date(8888, 1, 1, 1, 1, 1, 1, time.UTC)),
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 9999,
					Free:  999,
				},
			},
		},
		"should ensure that the hypervisor meets the minimum RAM requirements": {
			DeadRow: []*apiv4.OrchestratorHypervisor{{
				ID: "smol :3",
			}},
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
		Hypers   []*apiv4.OrchestratorHypervisor
		Expected *apiv4.OrchestratorHypervisor
	}{
		"should work correctly": {
			Hypers: []*apiv4.OrchestratorHypervisor{
				{
					ID:         "not to destroy",
					OnlyForced: true,
				},
				{
					ID:              "to destroy",
					OnlyForced:      true,
					DesktopsStarted: 1000,
					DestroyTime:     apiv4.NewNilDateTime(now.Add(-1 * time.Hour)),
				},
			},
			Expected: &apiv4.OrchestratorHypervisor{
				ID:              "to destroy",
				OnlyForced:      true,
				DesktopsStarted: 1000,
				DestroyTime:     apiv4.NewNilDateTime(now.Add(-1 * time.Hour)),
			},
		},
		"should remove a desktop with a destroy time and 0 desktops": {
			Hypers: []*apiv4.OrchestratorHypervisor{
				{
					ID:         "not to destroy",
					OnlyForced: true,
				},
				{
					ID:              "to destroy",
					OnlyForced:      true,
					DesktopsStarted: 0,
					DestroyTime:     apiv4.NewNilDateTime(now.Add(1 * time.Hour)),
				},
			},
			Expected: &apiv4.OrchestratorHypervisor{
				ID:              "to destroy",
				OnlyForced:      true,
				DesktopsStarted: 0,
				DestroyTime:     apiv4.NewNilDateTime(now.Add(1 * time.Hour)),
			},
		},
		"should avoid killing hypervisors that aren't in only forced, due a mismanagement": {
			Hypers: []*apiv4.OrchestratorHypervisor{
				{
					ID:              "not to destroy",
					OnlyForced:      false,
					DesktopsStarted: 1000,
					DestroyTime:     apiv4.NewNilDateTime(now.Add(-1 * time.Hour)),
				},
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
		HypersToAcknowledge []*apiv4.OrchestratorHypervisor
		HypersToManage      []*apiv4.OrchestratorHypervisor
		RAMAvail            int
		MinRAM              int
		MaxRAM              int
		MinRAMLimitPercent  int
		MinRAMLimitMargin   int
		MaxRAMLimitPercent  int
		MaxRAMLimitMargin   int
		Expected            *apiv4.OrchestratorHypervisor
	}{
		"should work correctly": {
			HypersToAcknowledge: []*apiv4.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "to sentence",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
				{
					ID: "GIGANTIC",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 10,
						Free:  10,
					},
				},
			},
			HypersToManage: []*apiv4.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "to sentence",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
				{
					ID: "GIGANTIC",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 10,
						Free:  10,
					},
				},
			},
			MinRAM:   10,
			MaxRAM:   12,
			RAMAvail: 13,
			Expected: &apiv4.OrchestratorHypervisor{
				ID: "to sentence",
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 2,
					Free:  2,
				},
			},
		},
		"should work correctly with only forced hypevisors": {
			HypersToAcknowledge: []*apiv4.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "normal",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
				{
					ID:         "GIGANTIC",
					OnlyForced: true,
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 10,
						Free:  10,
					},
				},
			},
			HypersToManage: []*apiv4.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "normal",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
				{
					ID:         "GIGANTIC",
					OnlyForced: true,
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 10,
						Free:  10,
					},
				},
			},
			MinRAM:   1,
			MaxRAM:   2,
			RAMAvail: 3,
			Expected: &apiv4.OrchestratorHypervisor{
				ID:         "GIGANTIC",
				OnlyForced: true,
				RAM: apiv4.OrchestratorResourceLoad{
					Total: 10,
					Free:  10,
				},
			},
		},
		"should not return any hypervisor if by removing it we don't meet the minRAM requirement": {
			HypersToAcknowledge: []*apiv4.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "can't sentence",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
			},
			HypersToManage: []*apiv4.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "can't sentence",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
			},
			MinRAM:   3,
			MaxRAM:   2,
			RAMAvail: 3,
		},
		"should ignore hypervisors already in the dead row": {
			HypersToAcknowledge: []*apiv4.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID:          "to ignore",
					DestroyTime: apiv4.NewNilDateTime(time.Now()),
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
			},
			HypersToManage: []*apiv4.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID:          "to ignore",
					DestroyTime: apiv4.NewNilDateTime(time.Now()),
					RAM: apiv4.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
			},
			MinRAM:   1,
			MaxRAM:   1,
			RAMAvail: 1,
		},
		"regression test #1": {
			HypersToAcknowledge: []*apiv4.OrchestratorHypervisor{{
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
			HypersToManage: []*apiv4.OrchestratorHypervisor{{
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
			}},
			RAMAvail:           2191950,
			MinRAMLimitPercent: 150,
			MinRAMLimitMargin:  1,
			MaxRAMLimitPercent: 150,
			MaxRAMLimitMargin:  112640,
			Expected: &apiv4.OrchestratorHypervisor{
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
			},
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
