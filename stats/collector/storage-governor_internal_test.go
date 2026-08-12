package collector

import (
	"context"
	"strings"
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
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

// collectAll drains a full Collect() against a stubbed governor payload and
// returns the rendered metric descriptors plus their label values.
func collectAll(t *testing.T, gov *apiv4.GovernorGaugesResponse) []prometheus.Metric {
	t.Helper()
	inv := apiv4.NewMockInvoker(t)
	inv.On("AdminQueuesGovernor", mock.Anything).Return(gov, nil)
	log := zerolog.Nop()
	s := NewStorageGovernor(context.Background(), &log, inv)

	ch := make(chan prometheus.Metric, 512)
	s.Collect(ch)
	close(ch)

	out := []prometheus.Metric{}
	for m := range ch {
		out = append(out, m)
	}
	return out
}

// labelsOf renders a metric's label values in Desc order.
func labelsOf(t *testing.T, m prometheus.Metric) map[string]string {
	t.Helper()
	var pb dto.Metric
	if err := m.Write(&pb); err != nil {
		t.Fatalf("write metric: %v", err)
	}
	out := map[string]string{}
	for _, l := range pb.GetLabel() {
		out[l.GetName()] = l.GetValue()
	}
	return out
}

// find returns the labels of every metric whose Desc mentions name.
func find(t *testing.T, ms []prometheus.Metric, name string) []map[string]string {
	t.Helper()
	out := []map[string]string{}
	for _, m := range ms {
		if strings.Contains(m.Desc().String(), `fqName: "isardvdi_storage_governor_`+name+`"`) {
			out = append(out, labelsOf(t, m))
		}
	}
	return out
}

// A fair-tier lane that is stranded, in the shape apiv4 really produces: the
// pool owns a category row, so its backlog is filed under that category and
// NOT under the pool-aggregate sentinel.
func strandedFairTierPayload() *apiv4.GovernorGaugesResponse {
	return &apiv4.GovernorGaugesResponse{
		Pools: []apiv4.PoolGauge{{
			Pool:    "default",
			Backlog: apiv4.NewOptPoolGaugeBacklog(apiv4.PoolGaugeBacklog{"bulk": 5}),
			Categories: []apiv4.CategoryGauge{{
				CategoryID: "_nocat",
				Backlog:    apiv4.NewOptCategoryGaugeBacklog(apiv4.CategoryGaugeBacklog{"bulk": 5}),
			}},
		}},
		Warnings: []apiv4.GovernorWarning{{
			Kind:          "stranded_lane",
			Pool:          apiv4.NewOptNilString("default"),
			Tier:          apiv4.NewOptNilString("bulk"),
			CategoryID:    apiv4.NewOptNilString("_nocat"),
			Backlog:       apiv4.NewOptNilInt(5),
			CoverageKnown: apiv4.NewOptNilBool(true),
		}},
	}
}

func TestStrandedLaneJoinsTheBacklogSeriesItAlarmsOn(t *testing.T) {
	assert := assert.New(t)
	ms := collectAll(t, strandedFairTierPayload())

	stranded := find(t, ms, "stranded_lane")
	assert.Len(stranded, 1, "the stranded lane must be exported")

	// The StrandedLane rule is `stranded_lane > 0 and on(pool, category, tier)
	// backlog > 0`, so a stranded series whose (pool, category, tier) matches no
	// backlog series can never fire — which is what labelling it with the
	// pool-aggregate sentinel did for every fair tier.
	backlogKeys := map[string]bool{}
	for _, l := range find(t, ms, "backlog") {
		backlogKeys[l["pool"]+"|"+l["category"]+"|"+l["tier"]] = true
	}
	key := stranded[0]["pool"] + "|" + stranded[0]["category"] + "|" + stranded[0]["tier"]
	assert.True(backlogKeys[key], "stranded_lane %s has no backlog series to join with (have %v)", key, backlogKeys)
}

func TestStrandedLanesOnTheSameTierStaySeparatePerCategory(t *testing.T) {
	assert := assert.New(t)
	gov := strandedFairTierPayload()
	gov.Pools[0].Categories = append(gov.Pools[0].Categories, apiv4.CategoryGauge{
		CategoryID: "catA",
		Backlog:    apiv4.NewOptCategoryGaugeBacklog(apiv4.CategoryGaugeBacklog{"bulk": 2}),
	})
	gov.Warnings = append(gov.Warnings, apiv4.GovernorWarning{
		Kind:          "stranded_lane",
		Pool:          apiv4.NewOptNilString("default"),
		Tier:          apiv4.NewOptNilString("bulk"),
		CategoryID:    apiv4.NewOptNilString("catA"),
		Backlog:       apiv4.NewOptNilInt(2),
		CoverageKnown: apiv4.NewOptNilBool(true),
	})

	// Two tenants stranded on the same tier are two incidents, and summing them
	// into one series loses which tenant to look at.
	got := map[string]float64{}
	for _, m := range collectAll(t, gov) {
		if !strings.Contains(m.Desc().String(), `fqName: "isardvdi_storage_governor_stranded_lane"`) {
			continue
		}
		var pb dto.Metric
		assert.NoError(m.Write(&pb))
		got[labelsOf(t, m)["category"]] = pb.GetGauge().GetValue()
	}
	assert.Equal(map[string]float64{"_nocat": 5, "catA": 2}, got)
}

func TestAReservedTierStrandedLaneStillJoins(t *testing.T) {
	assert := assert.New(t)
	// Reserved tiers have no per-category inflight, so their backlog is emitted
	// under the pool-aggregate sentinel and the warning must match it.
	gov := &apiv4.GovernorGaugesResponse{
		Pools: []apiv4.PoolGauge{{
			Pool:    "default",
			Backlog: apiv4.NewOptPoolGaugeBacklog(apiv4.PoolGaugeBacklog{"interactive": 3}),
		}},
		Warnings: []apiv4.GovernorWarning{{
			Kind:          "stranded_lane",
			Pool:          apiv4.NewOptNilString("default"),
			Tier:          apiv4.NewOptNilString("interactive"),
			Backlog:       apiv4.NewOptNilInt(3),
			CoverageKnown: apiv4.NewOptNilBool(true),
		}},
	}
	ms := collectAll(t, gov)
	stranded := find(t, ms, "stranded_lane")
	assert.Len(stranded, 1)
	assert.Equal(poolCategory, stranded[0]["category"])

	backlogKeys := map[string]bool{}
	for _, l := range find(t, ms, "backlog") {
		backlogKeys[l["pool"]+"|"+l["category"]+"|"+l["tier"]] = true
	}
	assert.True(backlogKeys["default|"+poolCategory+"|interactive"])
}
