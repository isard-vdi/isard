package collector

import (
	"context"
	"strconv"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-cli/pkg/client"
)

type IsardVDIAPI struct {
	Log *zerolog.Logger
	cli client.Interface

	descScrapeDuration               *prometheus.Desc
	descScrapeSuccess                *prometheus.Desc
	descUserInfo                     *prometheus.Desc
	descDesktopNumber                *prometheus.Desc
	descDesktopNumberStarted         *prometheus.Desc
	descDesktopNumberCategory        *prometheus.Desc
	descDesktopNumberCategoryStarted *prometheus.Desc
	descDesktopInfo                  *prometheus.Desc
	descTemplateNumber               *prometheus.Desc
	descTemplateNumberCategory       *prometheus.Desc
	descHypervisorInfo               *prometheus.Desc
	descDeploymentNumberCategory     *prometheus.Desc
}

func NewIsardVDIAPI(log *zerolog.Logger, cli *client.Client) *IsardVDIAPI {
	a := &IsardVDIAPI{
		Log: log,
		cli: cli,
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
	a.descUserInfo = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "user_info"),
		"Information of the user (such as the category and the group)",
		[]string{"id", "role", "category", "group"},
		prometheus.Labels{},
	)
	a.descDesktopNumber = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "desktop_number"),
		"The number of desktops",
		[]string{},
		prometheus.Labels{},
	)
	a.descDesktopNumberStarted = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "desktop_number_started"),
		"The number of desktops started",
		[]string{},
		prometheus.Labels{},
	)
	a.descDesktopNumberCategory = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "desktop_number_category"),
		"The number of desktops of a category",
		[]string{"category"},
		prometheus.Labels{},
	)
	a.descDesktopNumberCategoryStarted = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "desktop_number_category_started"),
		"The number of desktops of a category started",
		[]string{"category"},
		prometheus.Labels{},
	)
	a.descDesktopInfo = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "desktop_info"),
		"Information of the desktop (such as the user)",
		[]string{"id", "user"},
		prometheus.Labels{},
	)
	a.descTemplateNumber = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "template_number"),
		"The number of templates",
		[]string{},
		prometheus.Labels{},
	)
	a.descTemplateNumberCategory = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "template_number_category"),
		"The number of templates of a category",
		[]string{"category"},
		prometheus.Labels{},
	)
	a.descHypervisorInfo = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "hypervisor_info"),
		"Information of the hypervisor",
		[]string{"id", "status", "only_forced"},
		prometheus.Labels{},
	)
	a.descDeploymentNumberCategory = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "deployment_number_category"),
		"The number of deployments of a category",
		[]string{"category"},
		prometheus.Labels{},
	)

	return a
}

func (a *IsardVDIAPI) String() string {
	return "isardvdi_api"
}

func (a *IsardVDIAPI) Describe(ch chan<- *prometheus.Desc) {
	ch <- a.descScrapeDuration
	ch <- a.descScrapeSuccess
	ch <- a.descUserInfo
	ch <- a.descDesktopNumber
	ch <- a.descDesktopNumberStarted
	ch <- a.descDesktopNumberCategory
	ch <- a.descDesktopInfo
	ch <- a.descTemplateNumber
	ch <- a.descTemplateNumberCategory
	ch <- a.descHypervisorInfo
	ch <- a.descDeploymentNumberCategory
}

func (a *IsardVDIAPI) Collect(ch chan<- prometheus.Metric) {
	start := time.Now()

	success := 1

	usr, err := a.cli.StatsUsers(context.Background())
	if err != nil {
		a.Log.Info().Str("collector", a.String()).Err(err).Msg("list users")
		success = 0
	}

	for _, u := range usr {
		ch <- prometheus.MustNewConstMetric(a.descUserInfo, prometheus.GaugeValue, 1, client.GetString(u.ID), client.GetString(u.Role), client.GetString(u.Category), client.GetString(u.Group))
	}

	dsk, err := a.cli.StatsDesktops(context.Background())
	if err != nil {
		a.Log.Info().Str("collector", a.String()).Err(err).Msg("list desktops")
		success = 0
	}

	ch <- prometheus.MustNewConstMetric(a.descDesktopNumber, prometheus.GaugeValue, float64(len(dsk)))
	for _, d := range dsk {
		ch <- prometheus.MustNewConstMetric(a.descDesktopInfo, prometheus.GaugeValue, 1, client.GetString(d.ID), client.GetString(d.User))
	}

	cat, err := a.cli.StatsCategoryList(context.Background())
	if err != nil {
		a.Log.Info().Str("collector", a.String()).Err(err).Msg("get category statistics")
		success = 0
	}

	for _, c := range cat {
		ch <- prometheus.MustNewConstMetric(a.descDesktopNumberCategory, prometheus.GaugeValue, float64(client.GetInt(c.DesktopNum)), client.GetString(c.ID))
		ch <- prometheus.MustNewConstMetric(a.descTemplateNumberCategory, prometheus.GaugeValue, float64(client.GetInt(c.TemplateNum)), client.GetString(c.ID))
	}

	tmpl, err := a.cli.StatsTemplates(context.Background())
	if err != nil {
		a.Log.Info().Str("collector", a.String()).Err(err).Msg("list templates")
		success = 0
	}
	ch <- prometheus.MustNewConstMetric(a.descTemplateNumber, prometheus.GaugeValue, float64(len(tmpl)))

	hyp, err := a.cli.StatsHypervisors(context.Background())
	if err != nil {
		a.Log.Info().Str("collector", a.String()).Err(err).Msg("list hypervisors")
		success = 0
	}

	for _, h := range hyp {
		ch <- prometheus.MustNewConstMetric(a.descHypervisorInfo, prometheus.GaugeValue, 1, client.GetString(h.ID), string(*h.Status), strconv.FormatBool(client.GetBool(h.OnlyForced)))
	}

	dply, err := a.cli.StatsDeploymentByCategory(context.Background())
	if err != nil {
		a.Log.Info().Str("collector", a.String()).Err(err).Msg("get deployments statistics")
		success = 0
	}

	for _, d := range dply {
		ch <- prometheus.MustNewConstMetric(a.descDeploymentNumberCategory, prometheus.GaugeValue, float64(client.GetInt(d.DeploymentNum)), client.GetString(d.CategoryID))
	}

	duration := time.Since(start)

	ch <- prometheus.MustNewConstMetric(a.descScrapeDuration, prometheus.GaugeValue, duration.Seconds())
	ch <- prometheus.MustNewConstMetric(a.descScrapeSuccess, prometheus.GaugeValue, float64(success))
}
