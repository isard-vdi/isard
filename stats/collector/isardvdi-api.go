package collector

import (
	"context"
	"time"

	"github.com/golang-jwt/jwt"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-cli/pkg/client"
)

type IsardVDIAPI struct {
	Log    *zerolog.Logger
	cli    *client.Client
	secret string

	descScrapeDuration *prometheus.Desc
	descScrapeSuccess  *prometheus.Desc
	descUserInfo       *prometheus.Desc
	descDesktopNumber  *prometheus.Desc
	descDesktopInfo    *prometheus.Desc
	descTemplateNumber *prometheus.Desc
}

func NewIsardVDIAPI(log *zerolog.Logger, cli *client.Client, secret string) *IsardVDIAPI {
	a := &IsardVDIAPI{
		Log:    log,
		cli:    cli,
		secret: secret,
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
		[]string{"id", "category", "group"},
		prometheus.Labels{},
	)
	a.descDesktopNumber = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, a.String(), "desktop_number"),
		"The number of desktops",
		[]string{},
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
	ch <- a.descDesktopInfo
	ch <- a.descTemplateNumber
}

func (a *IsardVDIAPI) Collect(ch chan<- prometheus.Metric) {
	start := time.Now()

	tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &jwt.MapClaims{
		"kid": "isardvdi",
		"exp": start.Add(20 * time.Second).Unix(),
		"data": map[string]interface{}{
			"role_id":     "admin", // we need the role to be admin in order
			"category_id": "default",
			"user_id":     "local-default-admin-admin",
		},
	})

	success := 1
	ss, err := tkn.SignedString([]byte(a.secret))
	if err != nil {
		a.Log.Info().Str("collector", a.String()).Err(err).Msg("sign client token")
		success = 0
	}

	a.cli.Token = ss

	usr, err := a.cli.AdminUserList(context.Background())
	if err != nil {
		a.Log.Info().Str("collector", a.String()).Err(err).Msg("list users")
		success = 0
	}

	for _, u := range usr {
		ch <- prometheus.MustNewConstMetric(a.descUserInfo, prometheus.GaugeValue, 1, client.GetString(u.ID), client.GetString(u.Category), client.GetString(u.Group))
	}

	dsk, err := a.cli.AdminDesktopList(context.Background())
	if err != nil {
		a.Log.Info().Str("collector", a.String()).Err(err).Msg("list desktops")
		success = 0
	}

	ch <- prometheus.MustNewConstMetric(a.descDesktopNumber, prometheus.GaugeValue, float64(len(dsk)))
	for _, d := range dsk {
		ch <- prometheus.MustNewConstMetric(a.descDesktopInfo, prometheus.GaugeValue, 1, client.GetString(d.ID), client.GetString(d.User))
	}

	tmpl, err := a.cli.AdminTemplateList(context.Background())
	if err != nil {
		a.Log.Info().Str("collector", a.String()).Err(err).Msg("list templates")
		success = 0
	}
	ch <- prometheus.MustNewConstMetric(a.descTemplateNumber, prometheus.GaugeValue, float64(len(tmpl)))

	duration := time.Since(start)

	ch <- prometheus.MustNewConstMetric(a.descScrapeDuration, prometheus.GaugeValue, duration.Seconds())
	ch <- prometheus.MustNewConstMetric(a.descScrapeSuccess, prometheus.GaugeValue, float64(success))
}
