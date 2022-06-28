package collector

import (
	"context"
	"time"

	"github.com/oracle/oci-go-sdk/v65/common"
	"github.com/oracle/oci-go-sdk/v65/usageapi"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
)

type OCI struct {
	Log       *zerolog.Logger
	cli       usageapi.UsageapiClient
	lastQuery time.Time
	tenancy   string

	descScrapeDuration *prometheus.Desc
	descScrapeSuccess  *prometheus.Desc
	descDailyCost      *prometheus.Desc
	descMonthlyCost    *prometheus.Desc
}

func NewOCI(log *zerolog.Logger, cli usageapi.UsageapiClient, tenancy string) *OCI {
	o := &OCI{
		Log:       log,
		cli:       cli,
		lastQuery: time.Now().Add(-25 * time.Hour), // We set it to -25 hours to ensure that the first query is called upon the service start
		tenancy:   tenancy,
	}

	o.descScrapeDuration = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, o.String(), "scrape_duration_seconds"),
		"node_exporter: Duration of a collector scrape",
		[]string{},
		prometheus.Labels{},
	)
	o.descScrapeSuccess = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, o.String(), "scrape_duration_success"),
		"node_exporter: Whether a collector succeed",
		[]string{},
		prometheus.Labels{},
	)
	o.descDailyCost = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, o.String(), "daily_cost"),
		"The cost of an individual item of a service in OCI",
		[]string{"service", "description", "time"},
		prometheus.Labels{},
	)
	o.descMonthlyCost = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, o.String(), "monthly_cost"),
		"The cost of an individual item of a service in OCI during the last month",
		[]string{"service", "description", "time"},
		prometheus.Labels{},
	)

	return o
}

func (o *OCI) String() string {
	return "oci"
}

func (o *OCI) Describe(ch chan<- *prometheus.Desc) {
	ch <- o.descScrapeDuration
	ch <- o.descScrapeSuccess
	ch <- o.descDailyCost
}

func (o *OCI) Collect(ch chan<- prometheus.Metric) {
	start := time.Now()
	success := 1

	if o.lastQuery.Before(time.Now().Add(-24 * time.Hour)) {
		end := time.Now().Add(-24 * time.Hour)
		// Yesterday usage
		items, err := o.getUsage(end.Add(-24*time.Hour), end)
		if err != nil {
			o.Log.Info().Str("collector", o.String()).Err(err).Msg("query daily costs in the usageapi")
			success = 0
		}
		for _, i := range items {
			// Check that the item has a service, a 'description' and a cost
			if i.Service != nil && i.SkuName != nil && i.ComputedAmount != nil {
				ch <- prometheus.MustNewConstMetric(o.descDailyCost, prometheus.GaugeValue, float64(*i.ComputedAmount), *i.Service, *i.SkuName, end.Format(time.RFC3339))
			}
		}

		// Montly usage
		items, err = o.getUsage(time.Date(end.Year(), end.Month(), 1, 0, 0, 0, 0, end.Location()), end)
		if err != nil {
			o.Log.Info().Str("collector", o.String()).Err(err).Msg("query monthly costs in the usageapi")
			success = 0
		}
		for _, i := range items {
			// Check that the item has a service, a 'description' and a cost
			if i.Service != nil && i.SkuName != nil && i.ComputedAmount != nil {
				ch <- prometheus.MustNewConstMetric(o.descMonthlyCost, prometheus.GaugeValue, float64(*i.ComputedAmount), *i.Service, *i.SkuName, end.Format(time.RFC3339))
			}
		}

		o.lastQuery = time.Now()

		duration := time.Since(start)

		ch <- prometheus.MustNewConstMetric(o.descScrapeDuration, prometheus.GaugeValue, duration.Seconds())
		ch <- prometheus.MustNewConstMetric(o.descScrapeSuccess, prometheus.GaugeValue, float64(success))
	}
}

func (o *OCI) getUsage(start, end time.Time) ([]usageapi.UsageSummary, error) {
	var page *string
	finished := false

	items := []usageapi.UsageSummary{}

	for !finished {
		rsp, err := o.cli.RequestSummarizedUsages(context.Background(), usageapi.RequestSummarizedUsagesRequest{
			Page: page,
			RequestSummarizedUsagesDetails: usageapi.RequestSummarizedUsagesDetails{
				TenantId:          common.String(o.tenancy),
				Filter:            nil,
				Granularity:       usageapi.RequestSummarizedUsagesDetailsGranularityDaily,
				GroupBy:           []string{"service", "skuName"},
				TimeUsageEnded:    &common.SDKTime{Time: end.Truncate(24 * time.Hour)},
				TimeUsageStarted:  &common.SDKTime{Time: start.Truncate(24 * time.Hour)},
				IsAggregateByTime: common.Bool(true),
				QueryType:         usageapi.RequestSummarizedUsagesDetailsQueryTypeCost,
			},
		})
		if err != nil {
			return nil, err
		}

		items = append(items, rsp.Items...)

		if rsp.OpcNextPage != nil {
			page = rsp.OpcNextPage
		} else {
			finished = true
		}
	}

	return items, nil
}
