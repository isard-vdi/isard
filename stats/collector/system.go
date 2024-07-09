package collector

import (
	"fmt"
	"time"

	"gitlab.com/isard/isardvdi/stats/cfg"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
	"github.com/shirou/gopsutil/v4/cpu"
)

type System struct {
	domain string
	Log    *zerolog.Logger

	descScrapeDuration *prometheus.Desc
	descScrapeSuccess  *prometheus.Desc
	descCPUCores       *prometheus.Desc
	descCPUThreads     *prometheus.Desc
	descCPUFreq        *prometheus.Desc
	// descCPUUsage       *prometheus.Desc
}

func NewSystem(cfg cfg.Cfg, log *zerolog.Logger) *System {
	s := &System{domain: cfg.Domain, Log: log}

	s.descScrapeDuration = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, s.String(), "scrape_duration_seconds"),
		"node_exporter: Duration of a collector scrape",
		[]string{},
		prometheus.Labels{
			"domain": cfg.Domain,
		},
	)
	s.descScrapeSuccess = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, s.String(), "scrape_duration_success"),
		"node_exporter: Whether a collector succeed",
		[]string{},
		prometheus.Labels{
			"domain": cfg.Domain,
		},
	)
	s.descCPUCores = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, s.String(), "cpu_cores"),
		"The number of CPU cores",
		[]string{},
		prometheus.Labels{
			"domain": cfg.Domain,
		},
	)
	s.descCPUThreads = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, s.String(), "cpu_threads"),
		"The number of CPU threads",
		[]string{},
		prometheus.Labels{
			"domain": cfg.Domain,
		},
	)
	s.descCPUFreq = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, s.String(), "cpu_freq"),
		"The CPU frequency",
		[]string{},
		prometheus.Labels{
			"domain": cfg.Domain,
		},
	)
	// s.descCPUUsage = prometheus.NewDesc(
	// 	prometheus.BuildFQName(namespace, s.String(), "cpu_usage"),
	// 	"The CPU usage",
	// 	[]string{},
	// 	prometheus.Labels{
	// 		"domain": cfg.Domain,
	// 	},
	// )

	return s
}

func (s *System) String() string {
	return "system"
}

func (s *System) Describe(ch chan<- *prometheus.Desc) {
	ch <- s.descScrapeDuration
	ch <- s.descScrapeSuccess
	ch <- s.descCPUCores
	ch <- s.descCPUThreads
	ch <- s.descCPUFreq
	// ch <- s.descCPUUsage
}

func (s *System) Collect(ch chan<- prometheus.Metric) {
	start := time.Now()

	success := 1
	cpu, err := s.collectCPU()
	if err != nil {
		s.Log.Info().Str("collector", s.String()).Err(err).Msg("collect cpu")
		success = 0
	}

	ch <- prometheus.MustNewConstMetric(s.descCPUCores, prometheus.GaugeValue, float64(cpu["cores"]))
	ch <- prometheus.MustNewConstMetric(s.descCPUThreads, prometheus.GaugeValue, float64(cpu["threads"]))
	ch <- prometheus.MustNewConstMetric(s.descCPUFreq, prometheus.GaugeValue, float64(cpu["frequency"]))
	// ch <- prometheus.MustNewConstMetric(s.descCPUUsage, prometheus.GaugeValue, float64(cpu["usage"]))

	duration := time.Since(start)

	ch <- prometheus.MustNewConstMetric(s.descScrapeDuration, prometheus.GaugeValue, duration.Seconds())
	ch <- prometheus.MustNewConstMetric(s.descScrapeSuccess, prometheus.GaugeValue, float64(success))
}

func (s *System) collectCPU() (map[string]float64, error) {
	info, err := cpu.Info()
	if err != nil {
		return nil, fmt.Errorf("collect cpu stats: %w", err)
	}

	// usage, err := cpu.Percent(5*time.Second, false)
	// if err != nil {
	// 	return nil, fmt.Errorf("collect cpu usage: %w", err)
	// }

	return map[string]float64{
		"cores":     float64(info[0].Cores),
		"threads":   float64(len(info)),
		"frequency": info[0].Mhz,
		// "usage":     usage[0],
	}, nil
}
