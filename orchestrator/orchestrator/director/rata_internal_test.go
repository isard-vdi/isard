package director

import (
	"os"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi-sdk-go"
	"gitlab.com/isard/isardvdi/orchestrator/cfg"
	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
)

func TestMinRAM(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Hypers                  []*isardvdi.OrchestratorHypervisor
		MinRAM                  int
		MinRAMHourly            map[time.Weekday]map[time.Time]int
		MinRAMLimitPercent      int
		MinRAMLimitMargin       int
		MinRAMLimitMarginHourly map[time.Weekday]map[time.Time]int
		HyperMinRAM             int
		HyperMaxRAM             int
		Expected                int
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
			Hypers: []*isardvdi.OrchestratorHypervisor{
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
			Hypers: []*isardvdi.OrchestratorHypervisor{
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
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:                  "bm-e4-01",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				Buffering:           false,
				DestroyTime:         time.Time{},
				BookingsEndTime:     time.Time{},
				OrchestratorManaged: true,
				GPUOnly:             false,
				DesktopsStarted:     57,
				MinFreeMemGB:        190,
				CPU: isardvdi.OrchestratorResourceLoad{
					Total: 100,
					Used:  6,
					Free:  94,
				},
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 2051961,
					Used:  305801,
					Free:  1746160,
				},
			}, {
				ID:                  "bm-e2-02",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				Buffering:           false,
				DestroyTime:         time.Time{},
				BookingsEndTime:     time.Time{},
				OrchestratorManaged: false,
				GPUOnly:             false,
				DesktopsStarted:     23,
				MinFreeMemGB:        47,
				CPU: isardvdi.OrchestratorResourceLoad{
					Total: 100,
					Used:  7,
					Free:  93,
				},
				RAM: isardvdi.OrchestratorResourceLoad{
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
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:                  "bm-e2-02",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				Buffering:           false,
				DestroyTime:         time.Time{},
				BookingsEndTime:     time.Time{},
				OrchestratorManaged: false,
				GPUOnly:             false,
				DesktopsStarted:     23,
				MinFreeMemGB:        47,
				CPU: isardvdi.OrchestratorResourceLoad{
					Total: 100,
					Used:  7,
					Free:  93,
				},
				RAM: isardvdi.OrchestratorResourceLoad{
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
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{
				MinRAM:                  tc.MinRAM,
				MinRAMHourly:            tc.MinRAMHourly,
				MinRAMLimitPercent:      tc.MinRAMLimitPercent,
				MinRAMLimitMargin:       tc.MinRAMLimitMargin,
				MinRAMLimitMarginHourly: tc.MinRAMLimitMarginHourly,
				HyperMinRAM:             tc.HyperMinRAM,
				HyperMaxRAM:             tc.HyperMaxRAM,
			}, false, &log, nil)

			assert.Equal(tc.Expected, rata.minRAM(tc.Hypers))
		})
	}
}

func TestMaxRAM(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Hypers                  []*isardvdi.OrchestratorHypervisor
		MaxRAM                  int
		MaxRAMHourly            map[time.Weekday]map[time.Time]int
		MaxRAMLimitPercent      int
		MaxRAMLimitMargin       int
		MaxRAMLimitMarginHourly map[time.Weekday]map[time.Time]int
		Expected                int
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
			Hypers: []*isardvdi.OrchestratorHypervisor{
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
			Hypers: []*isardvdi.OrchestratorHypervisor{
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
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{
				MaxRAM:                  tc.MaxRAM,
				MaxRAMHourly:            tc.MaxRAMHourly,
				MaxRAMLimitPercent:      tc.MaxRAMLimitPercent,
				MaxRAMLimitMargin:       tc.MaxRAMLimitMargin,
				MaxRAMLimitMarginHourly: tc.MaxRAMLimitMarginHourly,
			}, false, &log, nil)

			assert.Equal(tc.Expected, rata.maxRAM(tc.Hypers))
		})
	}
}

func TestClassifyHypervisors(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Hypers                []*isardvdi.OrchestratorHypervisor
		ExpectedToAcknowledge []*isardvdi.OrchestratorHypervisor
		ExpectedToHandle      []*isardvdi.OrchestratorHypervisor
		ExpectedOnDeadRow     []*isardvdi.OrchestratorHypervisor
	}{
		"should classify the hypervisors correctly": {
			Hypers: []*isardvdi.OrchestratorHypervisor{
				{
					ID:     "hyper1",
					Status: isardvdi.HypervisorStatusOnline,
				},
				{
					ID:                  "hyper2",
					Status:              isardvdi.HypervisorStatusOnline,
					OrchestratorManaged: true,
				},
				{
					ID:                  "hyper3",
					Status:              isardvdi.HypervisorStatusOnline,
					OrchestratorManaged: true,
					DestroyTime:         time.Date(1, 2, 3, 4, 5, 6, 7, time.UTC),
				},
			},
			ExpectedToAcknowledge: []*isardvdi.OrchestratorHypervisor{
				{
					ID:     "hyper1",
					Status: isardvdi.HypervisorStatusOnline,
				},
				{
					ID:                  "hyper2",
					Status:              isardvdi.HypervisorStatusOnline,
					OrchestratorManaged: true,
				},
				{
					ID:                  "hyper3",
					Status:              isardvdi.HypervisorStatusOnline,
					OrchestratorManaged: true,
					DestroyTime:         time.Date(1, 2, 3, 4, 5, 6, 7, time.UTC),
				},
			},
			ExpectedToHandle: []*isardvdi.OrchestratorHypervisor{
				{
					ID:                  "hyper2",
					Status:              isardvdi.HypervisorStatusOnline,
					OrchestratorManaged: true,
				},
				{
					ID:                  "hyper3",
					Status:              isardvdi.HypervisorStatusOnline,
					OrchestratorManaged: true,
					DestroyTime:         time.Date(1, 2, 3, 4, 5, 6, 7, time.UTC),
				},
			},
			ExpectedOnDeadRow: []*isardvdi.OrchestratorHypervisor{
				{
					ID:                  "hyper3",
					Status:              isardvdi.HypervisorStatusOnline,
					OrchestratorManaged: true,
					DestroyTime:         time.Date(1, 2, 3, 4, 5, 6, 7, time.UTC),
				},
			},
		},
		"should ignore the offline hypervisors": {
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:     "offline",
				Status: isardvdi.HypervisorStatusOffline,
			}},
			ExpectedToAcknowledge: []*isardvdi.OrchestratorHypervisor{},
			ExpectedToHandle:      []*isardvdi.OrchestratorHypervisor{},
			ExpectedOnDeadRow:     []*isardvdi.OrchestratorHypervisor{},
		},
		"should ignore buffering hypervisors": {
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:        "buffering",
				Status:    isardvdi.HypervisorStatusOnline,
				Buffering: true,
			}},
			ExpectedToAcknowledge: []*isardvdi.OrchestratorHypervisor{},
			ExpectedToHandle:      []*isardvdi.OrchestratorHypervisor{},
			ExpectedOnDeadRow:     []*isardvdi.OrchestratorHypervisor{},
		},
		"should ignore GPU only hypervisors": {
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:      "gpu only",
				Status:  isardvdi.HypervisorStatusOnline,
				GPUOnly: true,
			}},
			ExpectedToAcknowledge: []*isardvdi.OrchestratorHypervisor{},
			ExpectedToHandle:      []*isardvdi.OrchestratorHypervisor{},
			ExpectedOnDeadRow:     []*isardvdi.OrchestratorHypervisor{},
		},
		"should not add only forced hypervisors to the acknowledge list": {
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:         "only forced",
				Status:     isardvdi.HypervisorStatusOnline,
				OnlyForced: true,
			}},
			ExpectedToAcknowledge: []*isardvdi.OrchestratorHypervisor{},
			ExpectedToHandle:      []*isardvdi.OrchestratorHypervisor{},
			ExpectedOnDeadRow:     []*isardvdi.OrchestratorHypervisor{},
		},
		"should not add a non orchestrator managed hypervisor to the handle list": {
			Hypers: []*isardvdi.OrchestratorHypervisor{{
				ID:                  "unmanaged",
				Status:              isardvdi.HypervisorStatusOnline,
				OrchestratorManaged: false,
			}},
			ExpectedToAcknowledge: []*isardvdi.OrchestratorHypervisor{{
				ID:                  "unmanaged",
				Status:              isardvdi.HypervisorStatusOnline,
				OrchestratorManaged: false,
			}},
			ExpectedToHandle:  []*isardvdi.OrchestratorHypervisor{},
			ExpectedOnDeadRow: []*isardvdi.OrchestratorHypervisor{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{}, false, &log, nil)

			hypersToAcknowledge, hypersToHandle, hypersOnDeadRow := rata.classifyHypervisors(tc.Hypers)

			assert.Equal(tc.ExpectedToAcknowledge, hypersToAcknowledge)
			assert.Equal(tc.ExpectedToHandle, hypersToHandle)
			assert.Equal(tc.ExpectedOnDeadRow, hypersOnDeadRow)
		})
	}
}

func TestBestHyperToCreate(t *testing.T) {

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
		"should return an error if there's no suitable hypervisor": {
			Hypers: []*operationsv1.ListHypervisorsResponseHypervisor{{
				Id:    "smol :3",
				Ram:   1,
				State: operationsv1.HypervisorState_HYPERVISOR_STATE_AVAILABLE_TO_CREATE,
			}},
			MinRAM:      2,
			ExpectedErr: "no hypervisor with the required resources and capabilities available",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
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
	assert := assert.New(t)

	cases := map[string]struct {
		DeadRow  []*isardvdi.OrchestratorHypervisor
		RAMAvail int
		MinCPU   int
		MinRAM   int
		Expected *isardvdi.OrchestratorHypervisor
	}{
		"should return the hypervisor that has the longest dead row sentence": {
			DeadRow: []*isardvdi.OrchestratorHypervisor{{
				ID:          "smol :3",
				DestroyTime: time.Date(9999, 1, 1, 1, 1, 1, 1, time.UTC),
			}, {
				ID:          "life sentence",
				DestroyTime: time.Date(8888, 1, 1, 1, 1, 1, 1, time.UTC),
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 9999,
					Free:  999,
				},
			}, {
				ID:          "short sentence",
				DestroyTime: time.Now(),
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 10,
					Free:  9,
				},
			}},
			MinRAM:   2,
			RAMAvail: 1,
			Expected: &isardvdi.OrchestratorHypervisor{
				ID:          "life sentence",
				DestroyTime: time.Date(8888, 1, 1, 1, 1, 1, 1, time.UTC),
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 9999,
					Free:  999,
				},
			},
		},
		"should ensure that the hypervisor meets the minimum RAM requirements": {
			DeadRow: []*isardvdi.OrchestratorHypervisor{{
				ID: "smol :3",
			}},
			MinRAM:   1,
			Expected: nil,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{}, false, &log, nil)

			assert.Equal(tc.Expected, rata.bestHyperToPardon(tc.DeadRow, tc.RAMAvail, tc.MinCPU, tc.MinRAM))
		})
	}
}

func TestBestHyperToDestroy(t *testing.T) {
	assert := assert.New(t)

	now := time.Now()

	cases := map[string]struct {
		Hypers   []*isardvdi.OrchestratorHypervisor
		Expected *isardvdi.OrchestratorHypervisor
	}{
		"should work correctly": {
			Hypers: []*isardvdi.OrchestratorHypervisor{
				{
					ID: "not to destroy",
				},
				{
					ID:              "to destroy",
					DesktopsStarted: 1000,
					DestroyTime:     now.Add(-1 * time.Hour),
				},
			},
			Expected: &isardvdi.OrchestratorHypervisor{
				ID:              "to destroy",
				DesktopsStarted: 1000,
				DestroyTime:     now.Add(-1 * time.Hour),
			},
		},
		"should remove a desktop with a destroy time and 0 desktops": {
			Hypers: []*isardvdi.OrchestratorHypervisor{
				{
					ID: "not to destroy",
				},
				{
					ID:              "to destroy",
					DesktopsStarted: 0,
					DestroyTime:     now.Add(1 * time.Hour),
				},
			},
			Expected: &isardvdi.OrchestratorHypervisor{
				ID:              "to destroy",
				DesktopsStarted: 0,
				DestroyTime:     now.Add(1 * time.Hour),
			},
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			rata := NewRata(cfg.DirectorRata{}, false, &log, nil)

			assert.Equal(tc.Expected, rata.bestHyperToDestroy(tc.Hypers))
		})
	}
}

func TestBestHyperToMoveInDeadRow(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		HypersToAcknowledge []*isardvdi.OrchestratorHypervisor
		HypersToManage      []*isardvdi.OrchestratorHypervisor
		RAMAvail            int
		MinRAM              int
		MaxRAM              int
		MinRAMLimitPercent  int
		MinRAMLimitMargin   int
		MaxRAMLimitPercent  int
		MaxRAMLimitMargin   int
		Expected            *isardvdi.OrchestratorHypervisor
	}{
		"should work correctly": {
			HypersToAcknowledge: []*isardvdi.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "to sentence",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
				{
					ID: "GIGANTIC",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 10,
						Free:  10,
					},
				},
			},
			HypersToManage: []*isardvdi.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "to sentence",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
				{
					ID: "GIGANTIC",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 10,
						Free:  10,
					},
				},
			},
			MinRAM:   10,
			MaxRAM:   12,
			RAMAvail: 13,
			Expected: &isardvdi.OrchestratorHypervisor{
				ID: "to sentence",
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 2,
					Free:  2,
				},
			},
		},
		"should work correctly with only forced hypevisors": {
			HypersToAcknowledge: []*isardvdi.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "normal",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
				{
					ID:         "GIGANTIC",
					OnlyForced: true,
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 10,
						Free:  10,
					},
				},
			},
			HypersToManage: []*isardvdi.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "normal",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
				{
					ID:         "GIGANTIC",
					OnlyForced: true,
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 10,
						Free:  10,
					},
				},
			},
			MinRAM:   1,
			MaxRAM:   2,
			RAMAvail: 3,
			Expected: &isardvdi.OrchestratorHypervisor{
				ID:         "GIGANTIC",
				OnlyForced: true,
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 10,
					Free:  10,
				},
			},
		},
		"should not return any hypervisor if by removing it we don't meet the minRAM requirement": {
			HypersToAcknowledge: []*isardvdi.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "can't sentence",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
			},
			HypersToManage: []*isardvdi.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID: "can't sentence",
					RAM: isardvdi.OrchestratorResourceLoad{
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
			HypersToAcknowledge: []*isardvdi.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID:          "to ignore",
					DestroyTime: time.Now(),
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 2,
						Free:  2,
					},
				},
			},
			HypersToManage: []*isardvdi.OrchestratorHypervisor{
				{
					ID: "smol :3",
					RAM: isardvdi.OrchestratorResourceLoad{
						Total: 1,
						Free:  1,
					},
				},
				{
					ID:          "to ignore",
					DestroyTime: time.Now(),
					RAM: isardvdi.OrchestratorResourceLoad{
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
			HypersToAcknowledge: []*isardvdi.OrchestratorHypervisor{{
				ID:                  "bm-e4-01",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				DesktopsStarted:     10,
				MinFreeMemGB:        190,
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 2051961,
					Used:  67556,
					Free:  1984404,
				},
			}, {
				ID:                  "bm-e2-02",
				Status:              isardvdi.HypervisorStatusOnline,
				DesktopsStarted:     2,
				OnlyForced:          false,
				OrchestratorManaged: false,
				MinFreeMemGB:        47,
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 515855,
					Used:  65620,
					Free:  450234,
				},
			}},
			HypersToManage: []*isardvdi.OrchestratorHypervisor{{
				ID:                  "bm-e4-01",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				DesktopsStarted:     10,
				MinFreeMemGB:        190,
				RAM: isardvdi.OrchestratorResourceLoad{
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
			Expected: &isardvdi.OrchestratorHypervisor{
				ID:                  "bm-e4-01",
				Status:              isardvdi.HypervisorStatusOnline,
				OnlyForced:          false,
				OrchestratorManaged: true,
				DesktopsStarted:     10,
				MinFreeMemGB:        190,
				RAM: isardvdi.OrchestratorResourceLoad{
					Total: 2051961,
					Used:  67556,
					Free:  1984404,
				},
			},
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
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
