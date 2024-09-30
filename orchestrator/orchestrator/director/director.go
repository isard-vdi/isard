package director

import (
	"context"
	"errors"
	"sort"
	"time"

	operationsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/operations/v1"
	"gitlab.com/isard/isardvdi/pkg/sdk"
)

var ErrNoHypervisorAvailable = errors.New("no hypervisor with the required resources and capabilities available")

var Available = []string{DirectorTypeRata, DirectorTypeChamaleon}

type Director interface {
	// NeedToScaleHypervisors states if there's a scale needed to be done.
	NeedToScaleHypervisors(ctx context.Context, operationsHypers []*operationsv1.ListHypervisorsResponseHypervisor, hypers []*sdk.OrchestratorHypervisor) (create *operationsv1.CreateHypervisorsRequest, remove *operationsv1.DestroyHypervisorsRequest, hyperToRemoveFromDeadRow []string, hyperToAddToDeadRow []string, err error)
	// ExtraOperations is a place for running infrastructure operations that don't fit in the other functions but are required
	ExtraOperations(ctx context.Context, hypers []*sdk.OrchestratorHypervisor) error
	String() string
}

func getCurrentHourlyLimit(limit map[time.Weekday]map[time.Time]int, now time.Time) int {
	weekdays := []time.Weekday{}
	for d := range limit {
		weekdays = append(weekdays, d)
	}

	sort.Slice(weekdays, func(i, j int) bool {
		return weekdays[i] < weekdays[j]
	})

	var weekday time.Weekday = -1
	for _, d := range weekdays {
		// If today is in the limit weekdays, use it
		if d == now.Weekday() {
			weekday = d
			break
		}

		// If we've "passed" today's weekday (e.g. today is wednesday and 'd' is thursday), use the last day that we had (tuesday)
		if d > now.Weekday() {
			// Unless there's no previous day. In that case, we should get the last day of the week available (e.g. today is monday, 'd' is tuesday. We should get sunday in that case [or whatever the last day is])
			if weekday == -1 {
				weekday = weekdays[len(weekdays)-1]
			}

			break
		}

		weekday = d
	}

	times := []time.Time{}
	for k := range limit[weekday] {
		times = append(times, k)
	}

	sort.Slice(times, func(i, j int) bool {
		return times[i].Before(times[j])
	})

	for i, t := range times {
		hour := time.Date(0, time.January, 1, now.Hour(), now.Minute(), 0, 0, time.UTC)

		if hour.Before(t) {
			// If is the first hour, it will take it as the first
			if i == 0 {
				return limit[weekday][t]
			}

			// If it's not the first, take the previous limit, since it's the active right now
			return limit[weekday][times[i-1]]
		}

		// If it's the last item in the list, take it, since it's the active right now
		if i == len(times)-1 {
			return limit[weekday][t]
		}
	}

	panic("invalid rata director hourly minimum")
}
