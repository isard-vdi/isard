package director

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestGetCurrentHourlyLimit(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Limit    map[time.Weekday]map[time.Time]int
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

	now := time.Date(0, time.January, 5, 15, 30, 0, 0, time.UTC)

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
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
