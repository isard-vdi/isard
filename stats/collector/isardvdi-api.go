package collector

import (
	"context"
	"fmt"
	"strconv"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
)

type IsardVDIAPI struct {
	Log *zerolog.Logger
	cli apiv4.Invoker
	ctx context.Context

	descScrapeDuration               *prometheus.Desc
	descScrapeSuccess                *prometheus.Desc
	descUserInfo                     *prometheus.Desc
	descDomainStatus                 *prometheus.Desc
	descDesktopNumber                *prometheus.Desc
	descDesktopNumberCategory        *prometheus.Desc
	descDesktopNumberCategoryStarted *prometheus.Desc
	descDesktopInfo                  *prometheus.Desc
	descTemplateNumber               *prometheus.Desc
	descTemplateNumberCategory       *prometheus.Desc
	descHypervisorInfo               *prometheus.Desc
	descDeploymentNumberCategory     *prometheus.Desc
}

func NewIsardVDIAPI(ctx context.Context, log *zerolog.Logger, cli apiv4.Invoker) *IsardVDIAPI {
	a := &IsardVDIAPI{
		Log: log,
		cli: cli,
		ctx: ctx,
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
	a.descDomainStatus = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "domain_status"),
		"Information of the number of domains of a domain type that have a specific status",
		[]string{"type", "status"},
		prometheus.Labels{},
	)
	a.descDesktopNumber = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "desktop_number"),
		"The number of desktops",
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
	ch <- a.descDomainStatus
	ch <- a.descDesktopNumber
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
	var successMu sync.Mutex
	failScrape := func() {
		successMu.Lock()
		success = 0
		successMu.Unlock()
	}

	type userMetric struct {
		id, role, category, group string
	}
	type domainStatusMetric struct {
		typ, status string
		number      float64
	}
	type desktopMetric struct {
		id, user string
	}
	type categoryMetric struct {
		id        string
		desktops  float64
		templates float64
	}
	type hypervisorMetric struct {
		id, status string
		onlyForced bool
	}
	type deploymentMetric struct {
		category string
		count    float64
	}

	var (
		users         []userMetric
		domainStatus  []domainStatusMetric
		desktops      []desktopMetric
		desktopNumber float64
		desktopsOK    bool
		categories    []categoryMetric
		templateCount float64
		templatesOK   bool
		hypervisors   []hypervisorMetric
		deployments   []deploymentMetric
	)

	var wg sync.WaitGroup

	wg.Go(func() {
		res, err := a.cli.StatsUsers(a.ctx)
		if err != nil {
			a.Log.Error().Str("collector", a.String()).Err(err).Msg("list users")
			failScrape()
			return
		}
		v, ok := res.(*apiv4.StatsUsersOKApplicationJSON)
		if !ok {
			a.Log.Error().Str("collector", a.String()).Str("type", fmt.Sprintf("%T", res)).Err(ogenclient.AsAPIError(res)).Msg("list users")
			failScrape()
			return
		}
		for _, u := range []apiv4.StatsKindUser(*v) {
			users = append(users, userMetric{id: u.ID, role: u.Role.Or(""), category: u.Category.Or(""), group: u.Group.Or("")})
		}
	})

	wg.Go(func() {
		res, err := a.cli.StatsDomainsStatus(a.ctx)
		if err != nil {
			a.Log.Error().Str("collector", a.String()).Err(err).Msg("get domains status")
			failScrape()
			return
		}
		v, ok := res.(*apiv4.StatsDomainsStatusResponse)
		if !ok {
			a.Log.Error().Str("collector", a.String()).Str("type", fmt.Sprintf("%T", res)).Err(ogenclient.AsAPIError(res)).Msg("get domains status")
			failScrape()
			return
		}
		if desktop, ok := v.Desktop.Get(); ok {
			for state, number := range desktop {
				domainStatus = append(domainStatus, domainStatusMetric{typ: "destkop", status: state, number: float64(number)})
			}
		}
		if template, ok := v.Template.Get(); ok {
			for state, number := range template {
				domainStatus = append(domainStatus, domainStatusMetric{typ: "template", status: state, number: float64(number)})
			}
		}
	})

	wg.Go(func() {
		res, err := a.cli.StatsDesktops(a.ctx)
		if err != nil {
			a.Log.Error().Str("collector", a.String()).Err(err).Msg("list desktops")
			failScrape()
			return
		}
		v, ok := res.(*apiv4.StatsDesktopsOKApplicationJSON)
		if !ok {
			a.Log.Error().Str("collector", a.String()).Str("type", fmt.Sprintf("%T", res)).Err(ogenclient.AsAPIError(res)).Msg("list desktops")
			failScrape()
			return
		}
		dsks := []apiv4.StatsKindDesktop(*v)
		desktopNumber = float64(len(dsks))
		desktopsOK = true
		for _, d := range dsks {
			desktops = append(desktops, desktopMetric{id: d.ID, user: d.User})
		}
	})

	wg.Go(func() {
		res, err := a.cli.StatsCategories(a.ctx)
		if err != nil {
			a.Log.Error().Str("collector", a.String()).Err(err).Msg("get category statistics")
			failScrape()
			return
		}
		v, ok := res.(*apiv4.StatsCategoriesResponse)
		if !ok {
			a.Log.Error().Str("collector", a.String()).Str("type", fmt.Sprintf("%T", res)).Err(ogenclient.AsAPIError(res)).Msg("get category statistics")
			failScrape()
			return
		}
		for catID, detail := range v.Category {
			categories = append(categories, categoryMetric{id: catID, desktops: float64(detail.Desktops.Total), templates: float64(detail.Templates.Total)})
		}
	})

	wg.Go(func() {
		res, err := a.cli.StatsTemplates(a.ctx)
		if err != nil {
			a.Log.Error().Str("collector", a.String()).Err(err).Msg("list templates")
			failScrape()
			return
		}
		v, ok := res.(*apiv4.StatsTemplatesOKApplicationJSON)
		if !ok {
			a.Log.Error().Str("collector", a.String()).Str("type", fmt.Sprintf("%T", res)).Err(ogenclient.AsAPIError(res)).Msg("list templates")
			failScrape()
			return
		}
		templateCount = float64(len([]apiv4.StatsKindTemplate(*v)))
		templatesOK = true
	})

	wg.Go(func() {
		res, err := a.cli.StatsHypervisors(a.ctx)
		if err != nil {
			a.Log.Error().Str("collector", a.String()).Err(err).Msg("list hypervisors")
			failScrape()
			return
		}
		v, ok := res.(*apiv4.StatsHypervisorsOKApplicationJSON)
		if !ok {
			a.Log.Error().Str("collector", a.String()).Str("type", fmt.Sprintf("%T", res)).Err(ogenclient.AsAPIError(res)).Msg("list hypervisors")
			failScrape()
			return
		}
		for _, h := range []apiv4.StatsKindHypervisor(*v) {
			hypervisors = append(hypervisors, hypervisorMetric{id: h.ID, status: h.Status, onlyForced: h.OnlyForced})
		}
	})

	wg.Go(func() {
		res, err := a.cli.StatsCategoriesDeployments(a.ctx)
		if err != nil {
			a.Log.Error().Str("collector", a.String()).Err(err).Msg("get deployments statistics")
			failScrape()
			return
		}
		v, ok := res.(*apiv4.StatsCategoriesDeploymentsResponse)
		if !ok {
			a.Log.Error().Str("collector", a.String()).Str("type", fmt.Sprintf("%T", res)).Err(ogenclient.AsAPIError(res)).Msg("get deployments statistics")
			failScrape()
			return
		}
		for catID, count := range v.Categories {
			deployments = append(deployments, deploymentMetric{category: catID, count: float64(count)})
		}
	})

	wg.Wait()

	for _, u := range users {
		ch <- prometheus.MustNewConstMetric(a.descUserInfo, prometheus.GaugeValue, 1, u.id, u.role, u.category, u.group)
	}
	for _, d := range domainStatus {
		ch <- prometheus.MustNewConstMetric(a.descDomainStatus, prometheus.GaugeValue, d.number, d.typ, d.status)
	}
	if desktopsOK {
		ch <- prometheus.MustNewConstMetric(a.descDesktopNumber, prometheus.GaugeValue, desktopNumber)
	}
	for _, d := range desktops {
		ch <- prometheus.MustNewConstMetric(a.descDesktopInfo, prometheus.GaugeValue, 1, d.id, d.user)
	}
	for _, c := range categories {
		ch <- prometheus.MustNewConstMetric(a.descDesktopNumberCategory, prometheus.GaugeValue, c.desktops, c.id)
		ch <- prometheus.MustNewConstMetric(a.descTemplateNumberCategory, prometheus.GaugeValue, c.templates, c.id)
	}
	if templatesOK {
		ch <- prometheus.MustNewConstMetric(a.descTemplateNumber, prometheus.GaugeValue, templateCount)
	}
	for _, h := range hypervisors {
		ch <- prometheus.MustNewConstMetric(a.descHypervisorInfo, prometheus.GaugeValue, 1, h.id, h.status, strconv.FormatBool(h.onlyForced))
	}
	for _, d := range deployments {
		ch <- prometheus.MustNewConstMetric(a.descDeploymentNumberCategory, prometheus.GaugeValue, d.count, d.category)
	}

	duration := time.Since(start)

	ch <- prometheus.MustNewConstMetric(a.descScrapeDuration, prometheus.GaugeValue, duration.Seconds())
	ch <- prometheus.MustNewConstMetric(a.descScrapeSuccess, prometheus.GaugeValue, float64(success))
}
