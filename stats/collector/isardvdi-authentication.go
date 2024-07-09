package collector

import (
	"encoding/json"
	"time"

	"github.com/grafana/loki/v3/pkg/logcli/client"
	"github.com/grafana/loki/v3/pkg/loghttp"
	"github.com/grafana/loki/v3/pkg/logproto"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
)

type IsardVDIAuthentication struct {
	Log       *zerolog.Logger
	cli       client.Client
	lastQuery time.Time

	descScrapeDuration *prometheus.Desc
	descScrapeSuccess  *prometheus.Desc
	descLoginSuccess   *prometheus.Desc
	descLoginFailed    *prometheus.Desc
}

func NewIsardVDIAuthentication(log *zerolog.Logger, cli client.Client) *IsardVDIAuthentication {
	a := &IsardVDIAuthentication{
		Log:       log,
		cli:       cli,
		lastQuery: time.Now(),
	}

	a.descScrapeDuration = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "scrape_duration_seconds"),
		"node_exporter: Duration of a collector scrape",
		[]string{},
		prometheus.Labels{},
	)
	a.descScrapeSuccess = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "scrape_duration_success"),
		"node_exporter: Whether a collector succeed",
		[]string{},
		prometheus.Labels{},
	)
	a.descLoginSuccess = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "login_success"),
		"Login success",
		[]string{"id"},
		prometheus.Labels{},
	)
	a.descLoginFailed = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "login_failed"),
		"The number of failed logins that there have been since the last time",
		[]string{},
		prometheus.Labels{},
	)

	return a
}

func (a *IsardVDIAuthentication) String() string {
	return "isardvdi_authentication"
}

func (a *IsardVDIAuthentication) Describe(ch chan<- *prometheus.Desc) {
	ch <- a.descScrapeDuration
	ch <- a.descScrapeSuccess
	ch <- a.descLoginSuccess
	ch <- a.descLoginFailed
}

func (a *IsardVDIAuthentication) Collect(ch chan<- prometheus.Metric) {
	start := time.Now()
	success := 1

	rsp, err := a.cli.Query(`{container_name="isard-authentication"}`, 5000, a.lastQuery, logproto.FORWARD, true)
	if err != nil {
		a.Log.Info().Str("collector", a.String()).Err(err).Msg("query loki")
		success = 0
	}

	var failed float64 = 0
	if success == 1 && rsp.Data.ResultType == loghttp.ResultTypeStream {

		for _, s := range rsp.Data.Result.(loghttp.Streams) {
			for _, e := range s.Entries {
				var items map[string]string
				if err := json.Unmarshal([]byte(e.Line), &items); err != nil {
					a.Log.Info().Str("collector", a.String()).Err(err).Msg("unmarshal authentication logs")
					success = 0
				}

				// TODO: This should be a constant in the authentication service
				if items["message"] == "login succeeded" {
					ch <- prometheus.MustNewConstMetric(a.descLoginSuccess, prometheus.CounterValue, 1, items["usr"])
					continue
				}

				// TODO: This should be a constant in the authentication service
				if items["error"] == "invalid credentials" {
					failed += 1
				}
			}

		}

	}

	a.lastQuery = time.Now()
	duration := time.Since(start)

	ch <- prometheus.MustNewConstMetric(a.descLoginFailed, prometheus.CounterValue, failed)
	ch <- prometheus.MustNewConstMetric(a.descScrapeDuration, prometheus.GaugeValue, duration.Seconds())
	ch <- prometheus.MustNewConstMetric(a.descScrapeSuccess, prometheus.GaugeValue, float64(success))
}
