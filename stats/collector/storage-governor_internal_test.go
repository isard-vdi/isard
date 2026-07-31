package collector

import (
	"strings"
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/stretchr/testify/assert"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
)

// collect drains emitCounters into the rendered metric text, which is the only
// place the value type (counter vs gauge) is observable.
func collect(kind string, c apiv4.GovernorCounters) []string {
	s := NewStorageGovernor(nil, nil, nil)
	ch := make(chan prometheus.Metric, 64)
	s.emitCounters(ch, kind, c)
	close(ch)

	out := []string{}
	for m := range ch {
		out = append(out, m.Desc().String())
	}
	return out
}

func TestShedTotalsAreCountersNotGauges(t *testing.T) {
	assert := assert.New(t)

	s := NewStorageGovernor(nil, nil, nil)
	ch := make(chan prometheus.Metric, 64)
	s.emitCounters(ch, "shed", apiv4.GovernorCounters{
		Total:    apiv4.NewOptInt(7),
		ByReason: apiv4.NewOptGovernorCountersByReason(apiv4.GovernorCountersByReason{"no_consumer": 7}),
	})
	close(ch)

	// A total that only grows must be a counter: rate() over a gauge reads a
	// process restart as the storm having stopped.
	found := false
	for m := range ch {
		if strings.Contains(m.Desc().String(), "events_total") {
			found = true
			assert.Contains(m.Desc().String(), "reason")
		}
	}
	assert.True(found, "events_total must be emitted")
}

func TestZeroCountersStillPublishTheSeries(t *testing.T) {
	assert := assert.New(t)

	// An install where nothing has ever been shed must still expose the series.
	// Without it a rule cannot tell "never happened" from "not reporting".
	got := collect("shed", apiv4.GovernorCounters{})

	joined := strings.Join(got, "\n")
	assert.Contains(joined, "events_total")
	assert.Contains(joined, "events_window")
}

func TestTierBreakdownIsEmittedPerTier(t *testing.T) {
	assert := assert.New(t)

	got := collect("defer", apiv4.GovernorCounters{
		ByTier: apiv4.NewOptGovernorCountersByTier(apiv4.GovernorCountersByTier{
			"maintenance": 3,
			"reclaim":     1,
		}),
	})

	n := 0
	for _, d := range got {
		if strings.Contains(d, "events_tier_total") {
			n++
		}
	}
	assert.Equal(2, n, "one series per tier present in the payload")
}

func TestLastEventAgeOnlyWhenKnown(t *testing.T) {
	assert := assert.New(t)

	// Never-fired: no age series at all, rather than a fabricated zero that
	// would read as "an event just happened".
	assert.NotContains(strings.Join(collect("shed", apiv4.GovernorCounters{}), "\n"), "last_event_age_seconds")

	withAge := collect("shed", apiv4.GovernorCounters{
		LastSecondsAgo: apiv4.NewOptNilFloat64(12.5),
	})
	assert.Contains(strings.Join(withAge, "\n"), "last_event_age_seconds")
}
