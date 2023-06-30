package director

import (
	"os"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi-sdk-go"
	"gitlab.com/isard/isardvdi/orchestrator/cfg"
)

func TestGetCurrentHourlyLimit(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Limit    map[time.Weekday]map[time.Time]int
		Now      time.Time
		Expected int
		Panic    string
	}{
		"should work as expected": {
			Limit: map[time.Weekday]map[time.Time]int{
				time.Saturday: {
					time.Date(0, time.January, 1, 18, 30, 0, 0, time.UTC): 3,
					time.Date(0, time.January, 1, 11, 30, 0, 0, time.UTC): 2,
					time.Date(0, time.January, 1, 10, 30, 0, 0, time.UTC): 1,
				},
			},
			Expected: 2,
		},
		"should work as expected 2": {
			Limit: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(0, time.January, 1, 0, 0, 0, 0, time.UTC):   102400,
					time.Date(0, time.January, 1, 8, 0, 0, 0, time.UTC):   327680,
					time.Date(0, time.January, 1, 12, 30, 0, 0, time.UTC): 153600,
					time.Date(0, time.January, 1, 16, 0, 0, 0, time.UTC):  256000,
					time.Date(0, time.January, 1, 17, 30, 0, 0, time.UTC): 153600,
					time.Date(0, time.January, 1, 19, 30, 0, 0, time.UTC): 102400,
				},
			},
			Expected: 153600,
		},
		"should work as expected 3": {
			Limit: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(0, time.January, 1, 0, 0, 0, 0, time.UTC):   102400,
					time.Date(0, time.January, 1, 8, 0, 0, 0, time.UTC):   327680,
					time.Date(0, time.January, 1, 12, 30, 0, 0, time.UTC): 153600,
					time.Date(0, time.January, 1, 16, 0, 0, 0, time.UTC):  256000,
					time.Date(0, time.January, 1, 17, 30, 0, 0, time.UTC): 153600,
					time.Date(0, time.January, 1, 19, 30, 0, 0, time.UTC): 102400,
				},
				time.Saturday: {
					time.Date(0, time.January, 1, 0, 0, 0, 0, time.UTC): 102400,
				},
			},
			Now:      time.Date(2023, time.April, 30, 10, 58, 36, 0, time.FixedZone("Europe/Madrid", 0)),
			Expected: 102400,
		},
		"should get the previous weekday correctly": {
			Limit: map[time.Weekday]map[time.Time]int{
				time.Tuesday: {
					time.Date(0, time.January, 1, 18, 30, 0, 0, time.UTC): 3,
					time.Date(0, time.January, 1, 11, 30, 0, 0, time.UTC): 2,
					time.Date(0, time.January, 1, 10, 30, 0, 0, time.UTC): 1,
				},
				time.Sunday: {
					time.Date(0, time.January, 1, 10, 30, 0, 0, time.UTC): 5,
				},
			},
			Expected: 2,
		},
		"should get the previous weekday (from previous week) correctly": {
			Limit: map[time.Weekday]map[time.Time]int{
				time.Sunday: {
					time.Date(0, time.January, 1, 18, 30, 0, 0, time.UTC): 3,
					time.Date(0, time.January, 1, 11, 30, 0, 0, time.UTC): 2,
					time.Date(0, time.January, 1, 10, 30, 0, 0, time.UTC): 1,
				},
				time.Friday: {
					time.Date(0, time.January, 1, 10, 30, 0, 0, time.UTC): 6,
				},
			},
			Expected: 2,
		},
		"should work as expected, with only one limit": {
			Limit: map[time.Weekday]map[time.Time]int{
				time.Wednesday: {
					time.Date(0, time.January, 1, 12, 30, 0, 0, time.UTC): 1,
				},
			},
			Expected: 1,
		},
		"should panic if it's empty": {
			Limit: map[time.Weekday]map[time.Time]int{},
			Panic: "invalid rata director hourly minimum",
		},
		"should pick the closest limit, if there's no previous limit": {
			Limit: map[time.Weekday]map[time.Time]int{
				time.Wednesday: {
					time.Date(0, time.January, 1, 20, 30, 0, 0, time.UTC): 2,
					time.Date(0, time.January, 1, 18, 30, 0, 0, time.UTC): 1,
				},
			},
			Expected: 1,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			now := tc.Now
			if now.IsZero() {
				now = time.Date(0, time.January, 5, 15, 30, 0, 0, time.UTC)
			}

			if tc.Panic != "" {
				assert.PanicsWithValue(tc.Panic, func() {
					getCurrentHourlyLimit(tc.Limit, now)
				})

			} else {
				assert.Equal(tc.Expected, getCurrentHourlyLimit(tc.Limit, now))
			}
		})
	}
}

func TestMinRAM(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Hypers                  []*isardvdi.OrchestratorHypervisor
		MinRAM                  int
		MinRAMHourly            map[time.Weekday]map[time.Time]int
		MinRAMLimitPercent      int
		MinRAMLimitMargin       int
		MinRAMLimitMarginHourly map[time.Weekday]map[time.Time]int
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
			}, false, &log, nil)

			assert.Equal(tc.Expected, rata.minRAM(tc.Hypers))
		})
	}
}
