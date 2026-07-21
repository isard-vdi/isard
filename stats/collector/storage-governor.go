package collector

import (
	"context"
	"fmt"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
)

// poolCategory is the sentinel category label for pool-aggregate rows (reserved
// tiers, and every tier on a flat/P1 install with no per-category lanes). Real
// per-category rows carry the category id (including "_nocat" for the
// null-category sentinel). Keeping the category label present on every
// backlog/oldest/failed/started series lets a single metric name carry both the
// pool aggregate and the per-tenant breakdown without a ragged label set.
const poolCategory = "_pool"

// reservedTiers never have per-category inflight (governor:running:<pool>:<cat>
// sets exist only for the fair tiers), so their backlog/oldest/failed is only
// ever pool-level. Mirrors queue_tiers._FAIR_TIERS being {bulk, background}.
var reservedTiers = map[string]bool{"interactive": true, "standard": true}

// StorageGovernor scrapes the apiv4 storage-governor gauge endpoint
// (GET /admin/items/queues/governor) and exports the tiered/governed storage
// scheduler's health as Prometheus gauges. apiv4 is the only aggregation point
// that can read both RethinkDB and the RQ Redis, so the exporter pulls from it
// rather than the RethinkDB-free storage worker exporting itself.
type StorageGovernor struct {
	Log *zerolog.Logger
	cli apiv4.Invoker
	ctx context.Context

	descScrapeDuration *prometheus.Desc
	descScrapeSuccess  *prometheus.Desc

	descHeavyRunning *prometheus.Desc
	descHeavyCap     *prometheus.Desc
	descHeavyLeak    *prometheus.Desc

	descPsiLimit           *prometheus.Desc
	descConfigEnabled      *prometheus.Desc
	descConfigMirrored     *prometheus.Desc
	descMultitenancyActive *prometheus.Desc
	descDataAgeSeconds     *prometheus.Desc
	descTruncatedLanes     *prometheus.Desc
	descTruncatedInflight  *prometheus.Desc

	descRedisUp              *prometheus.Desc
	descRedisPingMs          *prometheus.Desc
	descRedisUsedMemoryRatio *prometheus.Desc
	descRedisEvictedKeys     *prometheus.Desc

	descCategoryInflight *prometheus.Desc
	descCategoryCap      *prometheus.Desc
	descCategoryLeak     *prometheus.Desc
	descCategoryWeight   *prometheus.Desc
	descCategoryStarved  *prometheus.Desc
	descCategoryAtCap    *prometheus.Desc

	descBacklog            *prometheus.Desc
	descOldestQueuedAge    *prometheus.Desc
	descFailed             *prometheus.Desc
	descStartedOverTimeout *prometheus.Desc
	descStrandedLane       *prometheus.Desc

	descWorkerUp           *prometheus.Desc
	descWorkerHeartbeatAge *prometheus.Desc
	descWorkerPsiCPU       *prometheus.Desc
	descWorkerPsiIo        *prometheus.Desc
	descWorkerDeferring    *prometheus.Desc
}

func NewStorageGovernor(ctx context.Context, log *zerolog.Logger, cli apiv4.Invoker) *StorageGovernor {
	s := &StorageGovernor{Log: log, cli: cli, ctx: ctx}
	d := func(name, help string, labels ...string) *prometheus.Desc {
		return prometheus.NewDesc(
			prometheus.BuildFQName(namespace, s.String(), name),
			help, labels, prometheus.Labels{},
		)
	}

	s.descScrapeDuration = d("scrape_duration_seconds", "Duration of a collector scrape")
	s.descScrapeSuccess = d("scrape_duration_success", "Whether the collector scrape succeeded")

	s.descHeavyRunning = d("heavy_running", "Heavy jobs currently admitted (SCARD governor:heavy_running)")
	s.descHeavyCap = d("heavy_cap", "Effective global heavy-admission cap (max_heavy)")
	s.descHeavyLeak = d("heavy_leak", "Read-only leak delta on the heavy set (counted minus live)")

	s.descPsiLimit = d("psi_limit", "Effective PSI defer threshold the worker enforces")
	s.descConfigEnabled = d("config_enabled", "Governor gating enabled (1) or disabled kill-switch (0)")
	s.descConfigMirrored = d("config_mirrored", "governor:config in Redis matches the DB block (1) or drifted (0)")
	s.descMultitenancyActive = d("multitenancy_active", "Per-category (P2) mode reported by a live worker (1) or flat/P1 (0); absent when unknown")
	s.descDataAgeSeconds = d("data_age_seconds", "Age of the gauge snapshot the API answered with (frozen-cache honesty)")
	s.descTruncatedLanes = d("truncated_lanes", "Lanes dropped by the bounded scan cap")
	s.descTruncatedInflight = d("truncated_inflight", "In-flight members dropped by the bounded leak-scan cap")

	s.descRedisUp = d("redis_up", "RQ broker reachable (PING) (1) or down (0)")
	s.descRedisPingMs = d("redis_ping_ms", "RQ broker PING latency in milliseconds")
	s.descRedisUsedMemoryRatio = d("redis_used_memory_ratio", "RQ broker used_memory / maxmemory")
	s.descRedisEvictedKeys = d("redis_evicted_keys", "RQ broker evicted_keys counter (evictions silently corrupt SCARD gauges)")

	s.descCategoryInflight = d("category_inflight", "In-flight fair-tier jobs for a category (SCARD governor:running:<pool>:<cat>)", "pool", "category")
	s.descCategoryCap = d("category_cap", "Resolved per-category in-flight cap (fair tiers)", "pool", "category")
	s.descCategoryLeak = d("category_leak", "Read-only leak delta on a category's in-flight set", "pool", "category")
	s.descCategoryWeight = d("category_weight", "Weighted-round-robin weight of a category", "pool", "category")
	s.descCategoryStarved = d("category_starved", "Category has fair-tier backlog but zero in-flight while peers run (1)", "pool", "category")
	s.descCategoryAtCap = d("category_at_cap", "Category in-flight has reached its cap (1)", "pool", "category")

	s.descBacklog = d("backlog", "Queued jobs per lane; category=\"_pool\" is the pool aggregate for reserved/flat tiers", "pool", "category", "tier")
	s.descOldestQueuedAge = d("oldest_queued_age_seconds", "FIFO-head queued age per lane; category=\"_pool\" is the pool aggregate", "pool", "category", "tier")
	s.descFailed = d("failed", "Failed jobs per lane; category=\"_pool\" is the pool aggregate", "pool", "category", "tier")
	s.descStartedOverTimeout = d("started_over_timeout", "Started jobs past started_at+timeout (pool-level, category=\"_pool\")", "pool", "category", "tier")
	s.descStrandedLane = d("stranded_lane", "Backlog on a lane with a live worker but no consumer coverage (coverage_known only)", "pool", "category", "tier")

	s.descWorkerUp = d("worker_up", "Worker alive from heartbeat truth (SET member with a fresh hash) (1) or dead (0)", "worker", "pool", "kind")
	s.descWorkerHeartbeatAge = d("worker_heartbeat_age_seconds", "Seconds since the worker's last heartbeat", "worker")
	s.descWorkerPsiCPU = d("worker_psi_cpu", "Worker-reported CPU pressure (PSI some avg)", "worker")
	s.descWorkerPsiIo = d("worker_psi_io", "Worker-reported IO pressure (PSI some avg)", "worker")
	s.descWorkerDeferring = d("worker_deferring", "Worker is deferring background work under PSI (1)", "worker")

	return s
}

func (s *StorageGovernor) String() string {
	return "storage_governor"
}

func (s *StorageGovernor) Describe(ch chan<- *prometheus.Desc) {
	ch <- s.descScrapeDuration
	ch <- s.descScrapeSuccess
	ch <- s.descHeavyRunning
	ch <- s.descHeavyCap
	ch <- s.descHeavyLeak
	ch <- s.descPsiLimit
	ch <- s.descConfigEnabled
	ch <- s.descConfigMirrored
	ch <- s.descMultitenancyActive
	ch <- s.descDataAgeSeconds
	ch <- s.descTruncatedLanes
	ch <- s.descTruncatedInflight
	ch <- s.descRedisUp
	ch <- s.descRedisPingMs
	ch <- s.descRedisUsedMemoryRatio
	ch <- s.descRedisEvictedKeys
	ch <- s.descCategoryInflight
	ch <- s.descCategoryCap
	ch <- s.descCategoryLeak
	ch <- s.descCategoryWeight
	ch <- s.descCategoryStarved
	ch <- s.descCategoryAtCap
	ch <- s.descBacklog
	ch <- s.descOldestQueuedAge
	ch <- s.descFailed
	ch <- s.descStartedOverTimeout
	ch <- s.descStrandedLane
	ch <- s.descWorkerUp
	ch <- s.descWorkerHeartbeatAge
	ch <- s.descWorkerPsiCPU
	ch <- s.descWorkerPsiIo
	ch <- s.descWorkerDeferring
}

func boolToFloat(b bool) float64 {
	if b {
		return 1
	}
	return 0
}

func (s *StorageGovernor) Collect(ch chan<- prometheus.Metric) {
	start := time.Now()

	emitScrape := func(success float64) {
		ch <- prometheus.MustNewConstMetric(s.descScrapeDuration, prometheus.GaugeValue, time.Since(start).Seconds())
		ch <- prometheus.MustNewConstMetric(s.descScrapeSuccess, prometheus.GaugeValue, success)
	}

	res, err := s.cli.AdminQueuesGovernor(s.ctx)
	if err != nil {
		s.Log.Error().Str("collector", s.String()).Err(err).Msg("scrape storage governor")
		emitScrape(0)
		return
	}
	gov, ok := res.(*apiv4.GovernorGaugesResponse)
	if !ok {
		s.Log.Error().Str("collector", s.String()).Str("type", fmt.Sprintf("%T", res)).Err(ogenclient.AsAPIError(res)).Msg("scrape storage governor")
		emitScrape(0)
		return
	}

	gauge := func(desc *prometheus.Desc, v float64, labels ...string) {
		ch <- prometheus.MustNewConstMetric(desc, prometheus.GaugeValue, v, labels...)
	}

	// --- singletons -----------------------------------------------------
	if hg, ok := gov.Heavy.Get(); ok {
		gauge(s.descHeavyRunning, float64(hg.Running.Or(0)))
		gauge(s.descHeavyCap, float64(hg.Cap.Or(0)))
		gauge(s.descHeavyLeak, float64(hg.Leaked.Or(0)))
	}
	if v, ok := gov.PsiLimit.Get(); ok {
		gauge(s.descPsiLimit, v)
	}
	if v, ok := gov.ConfigEnabled.Get(); ok {
		gauge(s.descConfigEnabled, boolToFloat(v))
	}
	if v, ok := gov.ConfigMirrored.Get(); ok {
		gauge(s.descConfigMirrored, boolToFloat(v))
	}
	// multitenancy_active is bool|string("unknown"); export only the boolean —
	// absence of the series means "unknown", so an idle-but-unknown install
	// does not read as flat.
	if mt, ok := gov.MultitenancyActive.Get(); ok {
		if b, ok := mt.GetBool(); ok {
			gauge(s.descMultitenancyActive, boolToFloat(b))
		}
	}
	if v, ok := gov.DataAgeSeconds.Get(); ok {
		gauge(s.descDataAgeSeconds, v)
	}
	gauge(s.descTruncatedLanes, float64(gov.TruncatedLanes.Or(0)))
	gauge(s.descTruncatedInflight, float64(gov.TruncatedInflight.Or(0)))

	if rh, ok := gov.Redis.Get(); ok {
		gauge(s.descRedisUp, boolToFloat(rh.Up.Or(false)))
		if v, ok := rh.PingMs.Get(); ok {
			gauge(s.descRedisPingMs, v)
		}
		if v, ok := rh.UsedRatio.Get(); ok {
			gauge(s.descRedisUsedMemoryRatio, v)
		}
		gauge(s.descRedisEvictedKeys, float64(rh.EvictedKeys.Or(0)))
	}

	// --- pools / categories / lanes -------------------------------------
	for _, p := range gov.Pools {
		hasCats := len(p.Categories) > 0

		// Pool-aggregate lane series. For fair tiers we only emit the pool
		// aggregate when there are no per-category rows (flat/P1), so the
		// per-category rows below never double-count the same jobs.
		poolTier := func(tier string) bool { return reservedTiers[tier] || !hasCats }
		if m, ok := p.Backlog.Get(); ok {
			for tier, n := range m {
				if poolTier(tier) {
					gauge(s.descBacklog, float64(n), p.Pool, poolCategory, tier)
				}
			}
		}
		if m, ok := p.OldestQueuedAgeSeconds.Get(); ok {
			for tier, v := range m {
				if poolTier(tier) {
					gauge(s.descOldestQueuedAge, v, p.Pool, poolCategory, tier)
				}
			}
		}
		if m, ok := p.Failed.Get(); ok {
			for tier, n := range m {
				if poolTier(tier) {
					gauge(s.descFailed, float64(n), p.Pool, poolCategory, tier)
				}
			}
		}
		// started_over_timeout has no per-category breakdown in the payload.
		if m, ok := p.StartedOverTimeout.Get(); ok {
			for tier, n := range m {
				gauge(s.descStartedOverTimeout, float64(n), p.Pool, poolCategory, tier)
			}
		}

		for _, c := range p.Categories {
			gauge(s.descCategoryInflight, float64(c.Inflight.Or(0)), p.Pool, c.CategoryID)
			if v, ok := c.Cap.Get(); ok {
				gauge(s.descCategoryCap, float64(v), p.Pool, c.CategoryID)
			}
			gauge(s.descCategoryLeak, float64(c.Leaked.Or(0)), p.Pool, c.CategoryID)
			gauge(s.descCategoryWeight, float64(c.Weight.Or(0)), p.Pool, c.CategoryID)
			gauge(s.descCategoryStarved, boolToFloat(c.Starved.Or(false)), p.Pool, c.CategoryID)
			gauge(s.descCategoryAtCap, boolToFloat(c.AtCap.Or(false)), p.Pool, c.CategoryID)
			if m, ok := c.Backlog.Get(); ok {
				for tier, n := range m {
					gauge(s.descBacklog, float64(n), p.Pool, c.CategoryID, tier)
				}
			}
			if m, ok := c.OldestQueuedAgeSeconds.Get(); ok {
				for tier, v := range m {
					gauge(s.descOldestQueuedAge, v, p.Pool, c.CategoryID, tier)
				}
			}
			if m, ok := c.Failed.Get(); ok {
				for tier, n := range m {
					gauge(s.descFailed, float64(n), p.Pool, c.CategoryID, tier)
				}
			}
		}
	}

	// --- workers --------------------------------------------------------
	for _, w := range gov.Workers {
		gauge(s.descWorkerUp, boolToFloat(w.Up.Or(false)), w.Name, w.Pool.Or(""), w.Kind.Or(""))
		if v, ok := w.HeartbeatAgeSeconds.Get(); ok {
			gauge(s.descWorkerHeartbeatAge, v, w.Name)
		}
		if v, ok := w.PsiCPU.Get(); ok {
			gauge(s.descWorkerPsiCPU, v, w.Name)
		}
		if v, ok := w.PsiIo.Get(); ok {
			gauge(s.descWorkerPsiIo, v, w.Name)
		}
		gauge(s.descWorkerDeferring, boolToFloat(w.Deferring.Or(false)), w.Name)
	}

	// --- warnings -> derived gauges -------------------------------------
	// stranded_lane warnings carry no category_id and there can be several per
	// (pool, tier) — one per stranded fair-tier category — which would all map
	// to the same {pool, _pool, tier} series and make MustNewConstMetric emit a
	// duplicate. Sum them per (pool, tier) into one series. Only coverage-known
	// warnings are counted, so a rolling-upgrade unknown-coverage lane never
	// false-fires StrandedLane.
	type strandedKey struct{ pool, tier string }
	stranded := map[strandedKey]int{}
	for _, wn := range gov.Warnings {
		if wn.Kind == "stranded_lane" && wn.CoverageKnown.Or(false) {
			stranded[strandedKey{wn.Pool.Or(""), wn.Tier.Or("")}] += wn.Backlog.Or(0)
		}
	}
	for pt, backlog := range stranded {
		gauge(s.descStrandedLane, float64(backlog), pt.pool, poolCategory, pt.tier)
	}

	emitScrape(1)
}
