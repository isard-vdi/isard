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
			Panic: "invalid director hourly minimum",
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
		"regression test #1": {
			Limit: map[time.Weekday]map[time.Time]int{
				time.Monday: {
					time.Date(0, time.January, 1, 0, 0, 0, 0, time.UTC):   1,
					time.Date(0, time.January, 1, 7, 45, 0, 0, time.UTC):  614400,
					time.Date(0, time.January, 1, 10, 00, 0, 0, time.UTC): 307200,
					time.Date(0, time.January, 1, 12, 0, 0, 0, time.UTC):  614400,
					time.Date(0, time.January, 1, 13, 30, 0, 0, time.UTC): 102400,
					time.Date(0, time.January, 1, 15, 00, 0, 0, time.UTC): 614400,
					time.Date(0, time.January, 1, 20, 15, 0, 0, time.UTC): 1,
				},
				time.Saturday: {
					time.Date(0, time.January, 1, 0, 0, 0, 0, time.UTC): 1,
				},
			},
			Now:      time.Date(0, time.January, 5, 22, 45, 0, 0, time.UTC),
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
