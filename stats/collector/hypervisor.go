package collector

import (
	"time"

	"gitlab.com/isard/isardvdi/stats/cfg"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
)

type Hypervisor struct {
	hyp string
	Log *zerolog.Logger
	// libvirt pool retained for future use (the current Collect body does not
	// actually query libvirt — see commented-out calls below).
	libvirt *LibvirtPool

	descScrapeDuration *prometheus.Desc
	descScrapeSuccess  *prometheus.Desc
}

func NewHypervisor(cfg cfg.Cfg, log *zerolog.Logger, libvirtPool *LibvirtPool) *Hypervisor {
	h := &Hypervisor{
		hyp:     cfg.Domain,
		Log:     log,
		libvirt: libvirtPool,
	}

	h.descScrapeDuration = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, h.String(), "scrape_duration_seconds"),
		"node_exporter: Duration of a collector scrape",
		[]string{},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	h.descScrapeSuccess = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, h.String(), "scrape_duration_success"),
		"node_exporter: Whether a collector succeed",
		[]string{},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)

	return h
}

func (h *Hypervisor) String() string {
	return "hypervisor"
}

func (h *Hypervisor) Describe(ch chan<- *prometheus.Desc) {
	ch <- h.descScrapeDuration
	ch <- h.descScrapeSuccess
}

func (h *Hypervisor) Collect(ch chan<- prometheus.Metric) {
	// TODO: Is it interesting to get this?
	// h.conn.GetNodeInfo()
	// h.conn.GetLibVersion()
	start := time.Now()

	success := 1

	duration := time.Since(start)

	ch <- prometheus.MustNewConstMetric(h.descScrapeDuration, prometheus.GaugeValue, duration.Seconds())
	ch <- prometheus.MustNewConstMetric(h.descScrapeSuccess, prometheus.GaugeValue, float64(success))
}
