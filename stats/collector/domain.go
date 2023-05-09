package collector

import (
	"encoding/xml"
	"fmt"
	"log"
	"net"
	"strconv"
	"strings"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/stats/cfg"

	"github.com/patrickmn/go-cache"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
	"golang.org/x/crypto/ssh"
	"libvirt.org/go/libvirt"
	"libvirt.org/go/libvirtxml"
)

const viewersBasePort = 5900

type Domain struct {
	hyp         string
	Log         *zerolog.Logger
	libvirtMux  *sync.Mutex
	libvirtConn *libvirt.Connect
	sshMux      *sync.Mutex
	sshConn     *ssh.Client
	cache       *cache.Cache

	descScrapeDuration        *prometheus.Desc
	descScrapeSuccess         *prometheus.Desc
	descCPUTime               *prometheus.Desc
	descCPUUser               *prometheus.Desc
	descCPUSystem             *prometheus.Desc
	descBalloonCurrent        *prometheus.Desc
	descBalloonMaximum        *prometheus.Desc
	descBalloonSwapIn         *prometheus.Desc
	descBalloonSwapOut        *prometheus.Desc
	descBalloonMajorFault     *prometheus.Desc
	descBalloonMinorFault     *prometheus.Desc
	descBalloonUnused         *prometheus.Desc
	descBalloonAvailable      *prometheus.Desc
	descBalloonRss            *prometheus.Desc
	descBalloonUsable         *prometheus.Desc
	descBalloonLastUpdate     *prometheus.Desc
	descBalloonDiskCaches     *prometheus.Desc
	descBalloonHugetlbPgAlloc *prometheus.Desc
	descBalloonHugetlbPgFail  *prometheus.Desc
	descVCPUCurrent           *prometheus.Desc
	descVCPUState             *prometheus.Desc
	descVCPUTime              *prometheus.Desc
	descVCPUWait              *prometheus.Desc
	descVCPUDelay             *prometheus.Desc
	descVCPUHalted            *prometheus.Desc
	descNetRxBytes            *prometheus.Desc
	descNetRxPkts             *prometheus.Desc
	descNetRxErrs             *prometheus.Desc
	descNetRxDrop             *prometheus.Desc
	descNetTxBytes            *prometheus.Desc
	descNetTxPkts             *prometheus.Desc
	descNetTxErrs             *prometheus.Desc
	descNetTxDrop             *prometheus.Desc
	descBlockBackingIndex     *prometheus.Desc
	descBlockRdBytes          *prometheus.Desc
	descBlockRdReqs           *prometheus.Desc
	descBlockRdTimes          *prometheus.Desc
	descBlockWrBytes          *prometheus.Desc
	descBlockWrReqs           *prometheus.Desc
	descBlockWrTimes          *prometheus.Desc
	descBlockFlReqs           *prometheus.Desc
	descBlockFlTimes          *prometheus.Desc
	descBlockAllocation       *prometheus.Desc
	descBlockCapacity         *prometheus.Desc
	descBlockPhysical         *prometheus.Desc
	descMemAvailable          *prometheus.Desc
	descMemTotal              *prometheus.Desc
	descPortSpice             *prometheus.Desc
	descPortSpiceTLS          *prometheus.Desc
	descPortVNC               *prometheus.Desc
	descPortVNCWebsocket      *prometheus.Desc
}

func NewDomain(libvirtMux *sync.Mutex, sshMux *sync.Mutex, cfg cfg.Cfg, log *zerolog.Logger, libvirtConn *libvirt.Connect, sshConn *ssh.Client) *Domain {
	d := &Domain{
		libvirtMux:  libvirtMux,
		libvirtConn: libvirtConn,
		sshMux:      sshMux,
		sshConn:     sshConn,
		cache:       cache.New(6*time.Hour, time.Hour),
		Log:         log,
		hyp:         cfg.Domain,
	}

	d.descScrapeDuration = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "scrape_duration_seconds"),
		"node_exporter: Duration of a collector scrape",
		[]string{},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descScrapeSuccess = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "scrape_duration_success"),
		"node_exporter: Whether a collector succeed",
		[]string{},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descCPUTime = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "cpu_time"),
		"CPU Time",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descCPUUser = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "cpu_user"),
		"CPU User",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descCPUSystem = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "cpu_system"),
		"CPU System",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonCurrent = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_current"),
		"Current Balloon",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonMaximum = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_maximum"),
		"Maximum Balloon",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonSwapIn = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_swap_in"),
		"Balloon Swap In",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonSwapOut = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_swap_out"),
		"Balloon Swap Out",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonMajorFault = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_major_fault"),
		"Balloon major fault",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonMinorFault = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_minor_fault"),
		"Balloon minor fault",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonUnused = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_unused"),
		"Balloon unused",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonAvailable = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_available"),
		"Balloon available",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonRss = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_rss"),
		"Balloon rss",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonUsable = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_usable"),
		"Balloon usable",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonLastUpdate = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_last_update"),
		"Balloon last update",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonDiskCaches = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_disk_caches"),
		"Balloon disk caches",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonHugetlbPgAlloc = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_hugetlb_pg_alloc"),
		"Balloon hugeltb pg alloc",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBalloonHugetlbPgFail = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "balloon_hugetlb_pg_fail"),
		"Balloon hugeltb pg fail",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descVCPUCurrent = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "vcpu_current"),
		"VCPU current",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descVCPUState = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "vcpu_state"),
		"VCPU State",
		[]string{"desktop", "vcpu", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descVCPUTime = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "vcpu_time"),
		"VCPU Time",
		[]string{"desktop", "vcpu", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descVCPUWait = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "vcpu_wait"),
		"VCPU Wait",
		[]string{"desktop", "vcpu", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descVCPUDelay = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "vcpu_delay"),
		"VCPU Delay",
		[]string{"desktop", "vcpu", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descVCPUHalted = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "vcpu_halted"),
		"VCPU Halted",
		[]string{"desktop", "vcpu", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descNetRxBytes = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "net_rx_bytes"),
		"Network Rx bytes",
		[]string{"desktop", "net", "mac", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descNetRxPkts = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "net_rx_pkts"),
		"Network Rx packets",
		[]string{"desktop", "net", "mac", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descNetRxErrs = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "net_rx_errors"),
		"Network Rx errors",
		[]string{"desktop", "net", "mac", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descNetRxDrop = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "net_rx_drop"),
		"Network Rx drop",
		[]string{"desktop", "net", "mac", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descNetTxBytes = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "net_tx_bytes"),
		"Network Tx bytes",
		[]string{"desktop", "net", "mac", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descNetTxPkts = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "net_tx_pkts"),
		"Network Tx packets",
		[]string{"desktop", "net", "mac", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descNetTxErrs = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "net_tx_errors"),
		"Network Tx errors",
		[]string{"desktop", "net", "mac", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descNetTxDrop = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "net_tx_drop"),
		"Network Rx drop",
		[]string{"desktop", "net", "mac", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockBackingIndex = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_backing_index"),
		"Block backing chain index",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockRdBytes = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_rd_bytes"),
		"Block rd bytes",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockRdReqs = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_rd_reqs"),
		"Block rd reqs",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockRdTimes = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_rd_times"),
		"Block rd times",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockWrBytes = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_wr_bytes"),
		"Block wr bytes",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockWrReqs = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_wr_reqs"),
		"Block wr reqs",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockWrTimes = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_wr_times"),
		"Block wr times",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockFlReqs = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_fl_reqs"),
		"Block fl reqs",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockFlTimes = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_fl_times"),
		"Block fl times",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockAllocation = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_allocation"),
		"Block allocation",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockCapacity = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_capacity"),
		"Block capacity",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descBlockPhysical = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "block_physical"),
		"Block physical",
		[]string{"desktop", "block_path", "block_name", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descMemAvailable = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "mem_available"),
		"Memory available",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descMemTotal = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "mem_total"),
		"Total memory",
		[]string{"desktop", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descPortSpice = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "port_spice"),
		"SPICE port",
		[]string{"desktop", "port", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descPortSpiceTLS = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "port_spice_tls"),
		"SPICE TLS port",
		[]string{"desktop", "port", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descPortVNC = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "port_vnc"),
		"VNC port",
		[]string{"desktop", "port", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	d.descPortVNCWebsocket = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "port_vnc_websocket"),
		"VNC Websocket port",
		[]string{"desktop", "port", "user_id", "group_id", "category_id"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)

	return d
}

func (d *Domain) String() string {
	return "domain"
}

func (d *Domain) Describe(ch chan<- *prometheus.Desc) {
	ch <- d.descScrapeDuration
	ch <- d.descScrapeSuccess
	ch <- d.descCPUTime
	ch <- d.descCPUUser
	ch <- d.descCPUSystem
	ch <- d.descBalloonCurrent
	ch <- d.descBalloonMaximum
	ch <- d.descBalloonSwapIn
	ch <- d.descBalloonSwapOut
	ch <- d.descBalloonMajorFault
	ch <- d.descBalloonMinorFault
	ch <- d.descBalloonUnused
	ch <- d.descBalloonAvailable
	ch <- d.descBalloonRss
	ch <- d.descBalloonUsable
	ch <- d.descBalloonLastUpdate
	ch <- d.descBalloonDiskCaches
	ch <- d.descBalloonHugetlbPgAlloc
	ch <- d.descBalloonHugetlbPgFail
	ch <- d.descVCPUCurrent
	ch <- d.descVCPUState
	ch <- d.descVCPUTime
	ch <- d.descVCPUWait
	ch <- d.descVCPUDelay
	ch <- d.descVCPUHalted
	ch <- d.descNetRxBytes
	ch <- d.descNetRxPkts
	ch <- d.descNetRxErrs
	ch <- d.descNetRxDrop
	ch <- d.descNetTxBytes
	ch <- d.descNetTxPkts
	ch <- d.descNetTxErrs
	ch <- d.descNetTxDrop
	ch <- d.descBlockBackingIndex
	ch <- d.descBlockRdBytes
	ch <- d.descBlockRdReqs
	ch <- d.descBlockRdTimes
	ch <- d.descBlockWrBytes
	ch <- d.descBlockWrReqs
	ch <- d.descBlockWrTimes
	ch <- d.descBlockFlReqs
	ch <- d.descBlockFlTimes
	ch <- d.descBlockAllocation
	ch <- d.descBlockCapacity
	ch <- d.descBlockPhysical
	ch <- d.descMemAvailable
	ch <- d.descMemTotal
	ch <- d.descPortSpice
	ch <- d.descPortSpiceTLS
	ch <- d.descPortVNC
	ch <- d.descPortVNCWebsocket
}

type metadata struct {
	XMLName       xml.Name       `xml:"metadata"`
	IsardMetadata *IsardMetadata `xml:"isard"`
}

type IsardMetadata struct {
	XMLName xml.Name          `xml:"isard"`
	Who     *IsardMetadataWho `xml:"who"`
}

type IsardMetadataWho struct {
	XMLName    xml.Name `xml:"who"`
	UserID     string   `xml:"user_id,attr"`
	GroupID    string   `xml:"group_id,attr"`
	CategoryID string   `xml:"category_id,attr"`
}

type cacheDomain struct {
	XML    *libvirtxml.Domain
	RawXML string
}

func (d *Domain) Collect(ch chan<- prometheus.Metric) {
	start := time.Now()

	success := 1
	stats, err := d.collectStats()
	if err != nil {
		d.Log.Error().Str("collector", d.String()).Err(err).Msg("collect stats")
		success = 0
	}

	for _, s := range stats {
		id, domain, err, msg := d.getDomainXML(s)
		if err != nil {
			d.Log.Info().Str("collector", d.String()).Err(err).Msg(msg)

			continue
		}

		defer func() {
			d.libvirtMux.Lock()
			defer d.libvirtMux.Unlock()

			s.Domain.Free()
		}()

		var (
			userID     string
			groupID    string
			categoryID string
		)
		metadata, err := parseIsardMetadata(domain.XML.Metadata)
		if err != nil {
			d.Log.Error().Str("collector", d.String()).Str("desktop", domain.XML.Name).Err(err).Msg("extract Isard metadata from domain")
		} else {
			userID = metadata.Who.UserID
			groupID = metadata.Who.GroupID
			categoryID = metadata.Who.CategoryID
		}

		if s.Cpu != nil {
			ch <- prometheus.MustNewConstMetric(d.descCPUTime, prometheus.GaugeValue, float64(s.Cpu.Time), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descCPUUser, prometheus.GaugeValue, float64(s.Cpu.User), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descCPUSystem, prometheus.GaugeValue, float64(s.Cpu.System), id, userID, groupID, categoryID)
		}

		if s.Balloon != nil {
			ch <- prometheus.MustNewConstMetric(d.descBalloonCurrent, prometheus.GaugeValue, float64(s.Balloon.Current), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonMaximum, prometheus.GaugeValue, float64(s.Balloon.Maximum), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonSwapIn, prometheus.GaugeValue, float64(s.Balloon.SwapIn), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonSwapOut, prometheus.GaugeValue, float64(s.Balloon.SwapOut), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonMajorFault, prometheus.GaugeValue, float64(s.Balloon.MajorFault), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonMinorFault, prometheus.GaugeValue, float64(s.Balloon.MinorFault), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonUnused, prometheus.GaugeValue, float64(s.Balloon.Unused), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonAvailable, prometheus.GaugeValue, float64(s.Balloon.Available), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonRss, prometheus.GaugeValue, float64(s.Balloon.Rss), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonUsable, prometheus.GaugeValue, float64(s.Balloon.Usable), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonLastUpdate, prometheus.GaugeValue, float64(s.Balloon.LastUpdate), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonDiskCaches, prometheus.GaugeValue, float64(s.Balloon.DiskCaches), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonHugetlbPgAlloc, prometheus.GaugeValue, float64(s.Balloon.HugetlbPgAlloc), id, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(d.descBalloonHugetlbPgFail, prometheus.GaugeValue, float64(s.Balloon.HugetlbPgFail), id, userID, groupID, categoryID)
		}

		if s.Vcpu != nil {
			ch <- prometheus.MustNewConstMetric(d.descVCPUCurrent, prometheus.GaugeValue, float64(len(s.Vcpu)), id, userID, groupID, categoryID)

			for i, v := range s.Vcpu {
				ch <- prometheus.MustNewConstMetric(d.descVCPUState, prometheus.GaugeValue, float64(v.State), id, strconv.Itoa(i), userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descVCPUTime, prometheus.GaugeValue, float64(v.Time), id, strconv.Itoa(i), userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descVCPUWait, prometheus.GaugeValue, float64(v.Wait), id, strconv.Itoa(i), userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descVCPUDelay, prometheus.GaugeValue, float64(int(v.Delay)), id, strconv.Itoa(i), userID, groupID, categoryID)

				var halted float64 = 0
				if v.Halted {
					halted = 1
				}
				ch <- prometheus.MustNewConstMetric(d.descVCPUHalted, prometheus.GaugeValue, halted, id, strconv.Itoa(i), userID, groupID, categoryID)
			}
		}

		if s.Net != nil {
			for _, n := range s.Net {
				mac := ""
				for _, i := range domain.XML.Devices.Interfaces {
					if i.Target.Dev == n.Name {
						mac = i.MAC.Address
					}
				}

				ch <- prometheus.MustNewConstMetric(d.descNetRxBytes, prometheus.GaugeValue, float64(n.RxBytes), id, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descNetRxPkts, prometheus.GaugeValue, float64(n.RxPkts), id, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descNetRxErrs, prometheus.CounterValue, float64(n.RxErrs), id, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descNetRxDrop, prometheus.GaugeValue, float64(n.RxDrop), id, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descNetTxBytes, prometheus.GaugeValue, float64(n.TxBytes), id, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descNetTxPkts, prometheus.GaugeValue, float64(n.TxPkts), id, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descNetTxErrs, prometheus.CounterValue, float64(n.TxErrs), id, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descNetTxDrop, prometheus.GaugeValue, float64(n.TxDrop), id, n.Name, mac, userID, groupID, categoryID)
			}
		}

		if s.Block != nil {
			for _, b := range s.Block {
				ch <- prometheus.MustNewConstMetric(d.descBlockBackingIndex, prometheus.GaugeValue, float64(b.BackingIndex), id, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descBlockRdBytes, prometheus.GaugeValue, float64(b.RdBytes), id, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descBlockRdReqs, prometheus.GaugeValue, float64(b.RdReqs), id, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descBlockRdTimes, prometheus.GaugeValue, float64(b.RdTimes), id, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descBlockWrBytes, prometheus.GaugeValue, float64(b.WrBytes), id, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descBlockWrTimes, prometheus.GaugeValue, float64(b.WrTimes), id, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descBlockWrReqs, prometheus.GaugeValue, float64(b.WrReqs), id, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descBlockFlTimes, prometheus.GaugeValue, float64(b.FlTimes), id, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descBlockFlReqs, prometheus.GaugeValue, float64(b.FlReqs), id, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descBlockAllocation, prometheus.GaugeValue, float64(b.Allocation), id, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descBlockCapacity, prometheus.GaugeValue, float64(b.Capacity), id, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(d.descBlockPhysical, prometheus.GaugeValue, float64(b.Physical), id, b.Path, b.Name, userID, groupID, categoryID)
			}
		}

		// TODO: Perf, DirtyRate?

		mem, err := d.collectMemStats(s.Domain)
		if err != nil {
			d.Log.Info().Str("collector", d.String()).Str("desktop", id).Err(err).Msg("collect memory stats")
			log.Println(err)
		}

		ch <- prometheus.MustNewConstMetric(d.descMemAvailable, prometheus.GaugeValue, mem["available"], id, userID, groupID, categoryID)
		ch <- prometheus.MustNewConstMetric(d.descMemTotal, prometheus.GaugeValue, mem["total"], id, userID, groupID, categoryID)

		ports, err := d.collectDomainPorts(id)
		if err != nil {
			d.Log.Info().Str("collector", d.String()).Str("desktop", id).Err(err).Msg("collect desktop ports")
		}

		if port, ok := ports["spice"]; ok {
			ch <- prometheus.MustNewConstMetric(d.descPortSpice, prometheus.GaugeValue, 1, id, strconv.Itoa(port), userID, groupID, categoryID)
		}

		if port, ok := ports["spice_tls"]; ok {
			ch <- prometheus.MustNewConstMetric(d.descPortSpiceTLS, prometheus.GaugeValue, 1, id, strconv.Itoa(port), userID, groupID, categoryID)
		}

		if port, ok := ports["vnc"]; ok {
			ch <- prometheus.MustNewConstMetric(d.descPortVNC, prometheus.GaugeValue, 1, id, strconv.Itoa(port), userID, groupID, categoryID)
		}

		if port, ok := ports["vnc_websocket"]; ok {
			ch <- prometheus.MustNewConstMetric(d.descPortVNCWebsocket, prometheus.GaugeValue, 1, id, strconv.Itoa(port), userID, groupID, categoryID)
		}
	}

	duration := time.Since(start)

	ch <- prometheus.MustNewConstMetric(d.descScrapeDuration, prometheus.GaugeValue, duration.Seconds())
	ch <- prometheus.MustNewConstMetric(d.descScrapeSuccess, prometheus.GaugeValue, float64(success))
}

func (d *Domain) getDomainXML(s libvirt.DomainStats) (string, cacheDomain, error, string) {
	d.libvirtMux.Lock()
	defer d.libvirtMux.Unlock()

	id, err := s.Domain.GetName()
	if err != nil {
		return id, cacheDomain{}, err, "get domain name"
	}

	cacheDom, ok := d.cache.Get(id)
	var domain cacheDomain
	if !ok {
		raw, err := s.Domain.GetXMLDesc(0)
		if err != nil {
			return id, cacheDomain{}, err, "get domain XML"
		}

		xml := &libvirtxml.Domain{}
		if err := xml.Unmarshal(raw); err != nil {
			return id, cacheDomain{}, err, "unmarshal domain XML"
		}

		domain = cacheDomain{XML: xml, RawXML: raw}

		d.cache.Add(id, domain, cache.DefaultExpiration)
	} else {
		domain = cacheDom.(cacheDomain)
	}

	return id, domain, nil, ""
}

func (d *Domain) collectStats() ([]libvirt.DomainStats, error) {
	d.libvirtMux.Lock()
	defer d.libvirtMux.Unlock()

	// TODO: Test if getting a batch of domain stats performs better than getting 1 domain each time

	stats, err := d.libvirtConn.GetAllDomainStats(nil, 0, libvirt.CONNECT_GET_ALL_DOMAINS_STATS_RUNNING)
	if err != nil {
		return nil, fmt.Errorf("get the domain stats: %w", err)
	}

	return stats, nil
}

func (d *Domain) collectMemStats(dom *libvirt.Domain) (map[string]float64, error) {
	d.libvirtMux.Lock()
	defer d.libvirtMux.Unlock()

	mem, err := dom.MemoryStats(uint32(libvirt.DOMAIN_MEMORY_STAT_NR), 0)
	if err != nil {
		return nil, fmt.Errorf("get the domain memory stats: %w", err)
	}

	res := map[string]float64{}
	for _, m := range mem {
		switch m.Tag {
		case int32(libvirt.DOMAIN_MEMORY_STAT_UNUSED):
			res["available"] = float64(m.Val)

		case int32(libvirt.DOMAIN_MEMORY_STAT_AVAILABLE):
			res["total"] = float64(m.Val)
		}
	}

	return res, nil
}

func (d *Domain) collectDomainPorts(id string) (map[string]int, error) {
	d.sshMux.Lock()
	defer d.sshMux.Unlock()

	sess, err := d.sshConn.NewSession()
	if err != nil {
		return nil, fmt.Errorf("create ssh session: %w", err)
	}
	defer sess.Close()

	b, err := sess.CombinedOutput(fmt.Sprintf(`cat /var/log/libvirt/qemu/%s.log | grep -e tls-port -e websocket | tail -n 2`, id))
	if err != nil {
		return nil, fmt.Errorf("collect domain ports: %w: %s", err, b)
	}

	ports := map[string]int{}

	// split the different options
	for _, s := range strings.Split(strings.Replace(string(b), "\\\n", ",", -1), ",") {
		// split the key and value
		opts := strings.Split(s, "=")
		if len(opts) == 2 {
			switch opts[0] {
			case "-spice port":
				i, err := strconv.Atoi(opts[1])
				if err != nil {
					return nil, fmt.Errorf("convert '%s' to number: %w", opts[1], err)
				}

				ports["spice"] = i

			case "tls-port":
				i, err := strconv.Atoi(opts[1])
				if err != nil {
					return nil, fmt.Errorf("convert '%s' to number: %w", opts[1], err)
				}

				ports["spice_tls"] = i

			case "websocket":
				i, err := strconv.Atoi(opts[1])
				if err != nil {
					return nil, fmt.Errorf("convert '%s' to number: %w", opts[1], err)
				}

				ports["vnc_websocket"] = i
			default:
			}
		}

		if strings.HasPrefix(s, "-vnc ") {
			_, port, err := net.SplitHostPort(strings.TrimPrefix(s, "-vnc "))
			if err != nil {
				return nil, fmt.Errorf("parse VNC port: %w", err)
			}

			i, err := strconv.Atoi(port)
			if err != nil {
				return nil, fmt.Errorf("convert '%s' to number: %w", port, err)
			}

			ports["vnc"] = viewersBasePort + i
		}
	}

	return ports, nil
}

func parseIsardMetadata(m *libvirtxml.DomainMetadata) (*IsardMetadata, error) {
	res := &metadata{}
	if err := xml.Unmarshal([]byte("<metadata>\n"+m.XML+"\n</metadata>"), res); err != nil {
		return nil, fmt.Errorf("parse Isard metadata: %w", err)
	}

	return res.IsardMetadata, nil
}
