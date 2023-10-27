package collector

import (
	"context"
	"encoding/xml"
	"fmt"
	"net"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"gitlab.com/isard/isardvdi/stats/cfg"

	"github.com/jellydator/ttlcache/v3"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
	"golang.org/x/crypto/ssh"
	"libvirt.org/go/libvirt"
	"libvirt.org/go/libvirtxml"
)

const (
	viewersBasePort = 5900
	domainBatchSize = 50
)

type DomainStats struct {
	stats    *libvirt.DomainStats
	mem      *DomainMem
	ports    DomainPorts
	xml      *libvirtxml.Domain
	metadata *IsardMetadata
}

type DomainPorts struct {
	spice        int
	spiceTls     int
	vncWebsocket int
	vnc          int
}

type DomainMem struct {
	total     float64
	available float64
}

type Domain struct {
	hyp             string
	log             *zerolog.Logger
	libvirtMux      *sync.Mutex
	libvirtConn     *libvirt.Connect
	sshMux          *sync.Mutex
	sshConn         *ssh.Client
	cache           *ttlcache.Cache[[2]string, DomainStats]
	extractDuration atomic.Pointer[time.Duration]

	descStatsExtractionDuration *prometheus.Desc
	descScrapeDuration          *prometheus.Desc
	descScrapeSuccess           *prometheus.Desc
	descCPUTime                 *prometheus.Desc
	descCPUUser                 *prometheus.Desc
	descCPUSystem               *prometheus.Desc
	descBalloonCurrent          *prometheus.Desc
	descBalloonMaximum          *prometheus.Desc
	descBalloonSwapIn           *prometheus.Desc
	descBalloonSwapOut          *prometheus.Desc
	descBalloonMajorFault       *prometheus.Desc
	descBalloonMinorFault       *prometheus.Desc
	descBalloonUnused           *prometheus.Desc
	descBalloonAvailable        *prometheus.Desc
	descBalloonRss              *prometheus.Desc
	descBalloonUsable           *prometheus.Desc
	descBalloonLastUpdate       *prometheus.Desc
	descBalloonDiskCaches       *prometheus.Desc
	descBalloonHugetlbPgAlloc   *prometheus.Desc
	descBalloonHugetlbPgFail    *prometheus.Desc
	descVCPUCurrent             *prometheus.Desc
	descVCPUState               *prometheus.Desc
	descVCPUTime                *prometheus.Desc
	descVCPUWait                *prometheus.Desc
	descVCPUDelay               *prometheus.Desc
	descVCPUHalted              *prometheus.Desc
	descNetRxBytes              *prometheus.Desc
	descNetRxPkts               *prometheus.Desc
	descNetRxErrs               *prometheus.Desc
	descNetRxDrop               *prometheus.Desc
	descNetTxBytes              *prometheus.Desc
	descNetTxPkts               *prometheus.Desc
	descNetTxErrs               *prometheus.Desc
	descNetTxDrop               *prometheus.Desc
	descBlockBackingIndex       *prometheus.Desc
	descBlockRdBytes            *prometheus.Desc
	descBlockRdReqs             *prometheus.Desc
	descBlockRdTimes            *prometheus.Desc
	descBlockWrBytes            *prometheus.Desc
	descBlockWrReqs             *prometheus.Desc
	descBlockWrTimes            *prometheus.Desc
	descBlockFlReqs             *prometheus.Desc
	descBlockFlTimes            *prometheus.Desc
	descBlockAllocation         *prometheus.Desc
	descBlockCapacity           *prometheus.Desc
	descBlockPhysical           *prometheus.Desc
	descMemAvailable            *prometheus.Desc
	descMemTotal                *prometheus.Desc
	descPortSpice               *prometheus.Desc
	descPortSpiceTLS            *prometheus.Desc
	descPortVNC                 *prometheus.Desc
	descPortVNCWebsocket        *prometheus.Desc
}

func NewDomain(ctx context.Context, libvirtMux *sync.Mutex, sshMux *sync.Mutex, cfg cfg.Cfg, log *zerolog.Logger, libvirtConn *libvirt.Connect, sshConn *ssh.Client) *Domain {
	// TODO: Setup domain cache expiration?
	d := &Domain{
		libvirtMux:  libvirtMux,
		libvirtConn: libvirtConn,
		sshMux:      sshMux,
		sshConn:     sshConn,
		hyp:         cfg.Domain,
		cache:       ttlcache.New[[2]string, DomainStats](),
	}
	l := log.With().Str("collector", d.String()).Str("hypervisor", d.hyp).Logger()
	d.log = &l

	zeroDur := time.Duration(0)
	d.extractDuration.Store(&zeroDur)

	go d.collectStats(ctx)

	d.descStatsExtractionDuration = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, d.String(), "stats_extraction_duration_seconds"),
		"node_exporter: Duration of a complete stats extraction (including all batches)",
		[]string{},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
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

func (c *Domain) String() string {
	return "domain"
}

func (c *Domain) Describe(ch chan<- *prometheus.Desc) {
	ch <- c.descScrapeDuration
	ch <- c.descScrapeSuccess
	ch <- c.descCPUTime
	ch <- c.descCPUUser
	ch <- c.descCPUSystem
	ch <- c.descBalloonCurrent
	ch <- c.descBalloonMaximum
	ch <- c.descBalloonSwapIn
	ch <- c.descBalloonSwapOut
	ch <- c.descBalloonMajorFault
	ch <- c.descBalloonMinorFault
	ch <- c.descBalloonUnused
	ch <- c.descBalloonAvailable
	ch <- c.descBalloonRss
	ch <- c.descBalloonUsable
	ch <- c.descBalloonLastUpdate
	ch <- c.descBalloonDiskCaches
	ch <- c.descBalloonHugetlbPgAlloc
	ch <- c.descBalloonHugetlbPgFail
	ch <- c.descVCPUCurrent
	ch <- c.descVCPUState
	ch <- c.descVCPUTime
	ch <- c.descVCPUWait
	ch <- c.descVCPUDelay
	ch <- c.descVCPUHalted
	ch <- c.descNetRxBytes
	ch <- c.descNetRxPkts
	ch <- c.descNetRxErrs
	ch <- c.descNetRxDrop
	ch <- c.descNetTxBytes
	ch <- c.descNetTxPkts
	ch <- c.descNetTxErrs
	ch <- c.descNetTxDrop
	ch <- c.descBlockBackingIndex
	ch <- c.descBlockRdBytes
	ch <- c.descBlockRdReqs
	ch <- c.descBlockRdTimes
	ch <- c.descBlockWrBytes
	ch <- c.descBlockWrReqs
	ch <- c.descBlockWrTimes
	ch <- c.descBlockFlReqs
	ch <- c.descBlockFlTimes
	ch <- c.descBlockAllocation
	ch <- c.descBlockCapacity
	ch <- c.descBlockPhysical
	ch <- c.descMemAvailable
	ch <- c.descMemTotal
	ch <- c.descPortSpice
	ch <- c.descPortSpiceTLS
	ch <- c.descPortVNC
	ch <- c.descPortVNCWebsocket
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

func (c *Domain) Collect(ch chan<- prometheus.Metric) {
	start := time.Now()

	success := 1
	for cacheID, item := range c.cache.Items() {
		name := getNameFromCacheID(cacheID)
		stats := item.Value()
		s := stats.stats

		var (
			userID     string
			groupID    string
			categoryID string
		)
		if stats.metadata != nil {
			userID = stats.metadata.Who.UserID
			groupID = stats.metadata.Who.GroupID
			categoryID = stats.metadata.Who.CategoryID
		}

		if s.Cpu != nil {
			ch <- prometheus.MustNewConstMetric(c.descCPUTime, prometheus.GaugeValue, float64(s.Cpu.Time), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descCPUUser, prometheus.GaugeValue, float64(s.Cpu.User), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descCPUSystem, prometheus.GaugeValue, float64(s.Cpu.System), name, userID, groupID, categoryID)
		}

		if s.Balloon != nil {
			ch <- prometheus.MustNewConstMetric(c.descBalloonCurrent, prometheus.GaugeValue, float64(s.Balloon.Current), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonMaximum, prometheus.GaugeValue, float64(s.Balloon.Maximum), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonSwapIn, prometheus.GaugeValue, float64(s.Balloon.SwapIn), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonSwapOut, prometheus.GaugeValue, float64(s.Balloon.SwapOut), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonMajorFault, prometheus.GaugeValue, float64(s.Balloon.MajorFault), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonMinorFault, prometheus.GaugeValue, float64(s.Balloon.MinorFault), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonUnused, prometheus.GaugeValue, float64(s.Balloon.Unused), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonAvailable, prometheus.GaugeValue, float64(s.Balloon.Available), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonRss, prometheus.GaugeValue, float64(s.Balloon.Rss), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonUsable, prometheus.GaugeValue, float64(s.Balloon.Usable), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonLastUpdate, prometheus.GaugeValue, float64(s.Balloon.LastUpdate), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonDiskCaches, prometheus.GaugeValue, float64(s.Balloon.DiskCaches), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonHugetlbPgAlloc, prometheus.GaugeValue, float64(s.Balloon.HugetlbPgAlloc), name, userID, groupID, categoryID)
			ch <- prometheus.MustNewConstMetric(c.descBalloonHugetlbPgFail, prometheus.GaugeValue, float64(s.Balloon.HugetlbPgFail), name, userID, groupID, categoryID)
		}

		if s.Vcpu != nil {
			ch <- prometheus.MustNewConstMetric(c.descVCPUCurrent, prometheus.GaugeValue, float64(len(s.Vcpu)), name, userID, groupID, categoryID)

			for i, v := range s.Vcpu {
				ch <- prometheus.MustNewConstMetric(c.descVCPUState, prometheus.GaugeValue, float64(v.State), name, strconv.Itoa(i), userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descVCPUTime, prometheus.GaugeValue, float64(v.Time), name, strconv.Itoa(i), userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descVCPUWait, prometheus.GaugeValue, float64(v.Wait), name, strconv.Itoa(i), userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descVCPUDelay, prometheus.GaugeValue, float64(int(v.Delay)), name, strconv.Itoa(i), userID, groupID, categoryID)

				var halted float64 = 0
				if v.Halted {
					halted = 1
				}
				ch <- prometheus.MustNewConstMetric(c.descVCPUHalted, prometheus.GaugeValue, halted, name, strconv.Itoa(i), userID, groupID, categoryID)
			}
		}

		if s.Net != nil && stats.xml != nil && stats.xml.Devices != nil {
			for _, n := range s.Net {
				mac := ""
				for _, i := range stats.xml.Devices.Interfaces {
					if i.Target.Dev == n.Name {
						mac = i.MAC.Address
					}
				}

				ch <- prometheus.MustNewConstMetric(c.descNetRxBytes, prometheus.GaugeValue, float64(n.RxBytes), name, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descNetRxPkts, prometheus.GaugeValue, float64(n.RxPkts), name, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descNetRxErrs, prometheus.CounterValue, float64(n.RxErrs), name, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descNetRxDrop, prometheus.GaugeValue, float64(n.RxDrop), name, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descNetTxBytes, prometheus.GaugeValue, float64(n.TxBytes), name, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descNetTxPkts, prometheus.GaugeValue, float64(n.TxPkts), name, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descNetTxErrs, prometheus.CounterValue, float64(n.TxErrs), name, n.Name, mac, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descNetTxDrop, prometheus.GaugeValue, float64(n.TxDrop), name, n.Name, mac, userID, groupID, categoryID)
			}
		}

		if s.Block != nil {
			for _, b := range s.Block {
				ch <- prometheus.MustNewConstMetric(c.descBlockBackingIndex, prometheus.GaugeValue, float64(b.BackingIndex), name, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descBlockRdBytes, prometheus.GaugeValue, float64(b.RdBytes), name, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descBlockRdReqs, prometheus.GaugeValue, float64(b.RdReqs), name, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descBlockRdTimes, prometheus.GaugeValue, float64(b.RdTimes), name, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descBlockWrBytes, prometheus.GaugeValue, float64(b.WrBytes), name, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descBlockWrTimes, prometheus.GaugeValue, float64(b.WrTimes), name, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descBlockWrReqs, prometheus.GaugeValue, float64(b.WrReqs), name, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descBlockFlTimes, prometheus.GaugeValue, float64(b.FlTimes), name, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descBlockFlReqs, prometheus.GaugeValue, float64(b.FlReqs), name, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descBlockAllocation, prometheus.GaugeValue, float64(b.Allocation), name, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descBlockCapacity, prometheus.GaugeValue, float64(b.Capacity), name, b.Path, b.Name, userID, groupID, categoryID)
				ch <- prometheus.MustNewConstMetric(c.descBlockPhysical, prometheus.GaugeValue, float64(b.Physical), name, b.Path, b.Name, userID, groupID, categoryID)
			}
		}

		ch <- prometheus.MustNewConstMetric(c.descMemAvailable, prometheus.GaugeValue, stats.mem.available, name, userID, groupID, categoryID)
		ch <- prometheus.MustNewConstMetric(c.descMemTotal, prometheus.GaugeValue, stats.mem.total, name, userID, groupID, categoryID)

		if stats.ports.spice != 0 {
			ch <- prometheus.MustNewConstMetric(c.descPortSpice, prometheus.GaugeValue, 1, name, strconv.Itoa(stats.ports.spice), userID, groupID, categoryID)
		}

		if stats.ports.spiceTls != 0 {
			ch <- prometheus.MustNewConstMetric(c.descPortSpiceTLS, prometheus.GaugeValue, 1, name, strconv.Itoa(stats.ports.spiceTls), userID, groupID, categoryID)
		}

		if stats.ports.vnc != 0 {
			ch <- prometheus.MustNewConstMetric(c.descPortVNC, prometheus.GaugeValue, 1, name, strconv.Itoa(stats.ports.vnc), userID, groupID, categoryID)
		}

		if stats.ports.vncWebsocket != 0 {
			ch <- prometheus.MustNewConstMetric(c.descPortVNCWebsocket, prometheus.GaugeValue, 1, name, strconv.Itoa(stats.ports.vncWebsocket), userID, groupID, categoryID)
		}
	}

	duration := time.Since(start)

	ch <- prometheus.MustNewConstMetric(c.descStatsExtractionDuration, prometheus.GaugeValue, c.extractDuration.Load().Seconds())
	ch <- prometheus.MustNewConstMetric(c.descScrapeDuration, prometheus.GaugeValue, duration.Seconds())
	ch <- prometheus.MustNewConstMetric(c.descScrapeSuccess, prometheus.GaugeValue, float64(success))
}

func (c *Domain) collectStats(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return

		default:
			var wg sync.WaitGroup

			wg.Add(1)
			go func() {
				defer wg.Done()

				defer func() {
					if r := recover(); r != nil {
						c.log.Error().Err(fmt.Errorf("%v", r)).Msg("recovered from panic")
					}
				}()

				start := time.Now()

				c.log.Trace().Msg("listing libvirt domains")
				c.libvirtMux.Lock()
				doms, err := c.libvirtConn.ListAllDomains(libvirt.CONNECT_LIST_DOMAINS_RUNNING)
				c.libvirtMux.Unlock()
				if err != nil {
					c.log.Error().Err(err).Msg("list all running domains")
					return
				}
				c.log.Debug().Int("running", len(doms)).Msg("libvirt domains listed")

				// Free the resources after usage? They probably don't need it
				// defer func() {
				// 	for _, d := range doms {
				// 		d.Free()
				// 	}
				// }()

				// Get the cached data and extract new data if the desktop isn't cached
				domsToExtract := []*libvirt.Domain{}
				domsCached := map[[2]string]DomainStats{}
				for _, d := range doms {
					cacheID, err := genCacheID(&d)
					if err != nil {
						c.log.Error().Err(err).Msg("get domain ID")
						continue
					}

					name := getNameFromCacheID(cacheID)

					cachedDom := c.cache.Get(cacheID)
					if cachedDom == nil {
						ports, err := c.collectDomainPorts(name)
						if err != nil {
							c.log.Error().Err(err).Str("id", name).Msg("collect domain ports")
							continue
						}

						domsCached[cacheID] = DomainStats{
							ports: ports,
						}

					} else {
						domsCached[cacheID] = cachedDom.Value()
					}

					domsToExtract = append(domsToExtract, &d)
				}

				c.log.Debug().Int("doms_to_extract", len(domsToExtract)).Msg("domains to extract")
				c.log.Debug().Int("doms_cached", len(domsCached)).Msg("domains cached")

				// Cleanup old cached domains
				for _, id := range c.cache.Keys() {
					if _, ok := domsCached[id]; !ok {
						// The domain is in the cache, but it's not running, so we delete it
						c.cache.Delete(id)
					}
				}

				// Split the stats extraction in batches
				batches := splitDomainsIntoBatches(domsToExtract)
				c.log.Debug().Int("num_batches", len(batches)).Int("batches_size", domainBatchSize).Msg("batches prepated")

				// Extract the stats
				for _, batch := range batches {
					c.log.Trace().Msg("extracting libvirt stats")

					c.libvirtMux.Lock()
					stats, err := c.libvirtConn.GetAllDomainStats(batch, 0, libvirt.CONNECT_GET_ALL_DOMAINS_STATS_RUNNING)
					c.libvirtMux.Unlock()
					if err != nil {
						c.log.Error().Err(err).Msg("extract domain stats")
						continue
					}

					c.log.Debug().Int("stats_number", len(stats)).Msg("stats batch extracted")

					for _, s := range stats {
						defer s.Domain.Free()

						cacheID, err := genCacheID(s.Domain)
						if err != nil {
							c.log.Error().Err(err).Msg("get domain ID")
							continue
						}

						name := getNameFromCacheID(cacheID)

						// TODO: Perf, DirtyRate?

						c.log.Debug().Str("id", name).Msg("extract domain memory stats")
						mem, err := c.collectMemStats(s.Domain)
						if err != nil {
							c.log.Error().Err(err).Str("id", name).Msg("extract memory stats")
							continue
						}

						cachedDom, ok := domsCached[cacheID]
						if !ok {
							c.log.Warn().Str("id", name).Msg("stats were extracted, but the domain wasn't cached")
							continue
						}

						if cachedDom.xml == nil || cachedDom.metadata == nil {
							c.log.Debug().Str("id", name).Msg("extract domain metadata")
							cachedDom.xml, cachedDom.metadata, err = c.collectDomainMetadata(s.Domain)
							if err != nil {
								c.log.Error().Err(err).Str("id", name).Msg("extract domain metadata")
							}
						}

						// Store the extracted stats in the cache, making it available to the collector
						c.cache.Set(cacheID, DomainStats{
							stats:    &s,
							mem:      mem,
							ports:    cachedDom.ports,
							xml:      cachedDom.xml,
							metadata: cachedDom.metadata,
						}, 0)
					}

					// Wait 2 seconds between batches to ensure we're not killing libvirt
					time.Sleep(2 * time.Second)
				}

				duration := time.Since(start)
				c.extractDuration.Store(&duration)

				c.log.Info().Dur("duration", duration).Msg("stats extracted")
			}()

			wg.Wait()
		}

		// Wait 30 seconds between stats extraction
		time.Sleep(30 * time.Second)
	}
}

func (c *Domain) collectMemStats(dom *libvirt.Domain) (*DomainMem, error) {
	c.libvirtMux.Lock()
	defer c.libvirtMux.Unlock()

	mem, err := dom.MemoryStats(uint32(libvirt.DOMAIN_MEMORY_STAT_NR), 0)
	if err != nil {
		return nil, fmt.Errorf("get the domain memory stats: %w", err)
	}

	res := &DomainMem{}
	for _, m := range mem {
		switch m.Tag {
		case int32(libvirt.DOMAIN_MEMORY_STAT_UNUSED):
			res.available = float64(m.Val)

		case int32(libvirt.DOMAIN_MEMORY_STAT_AVAILABLE):
			res.total = float64(m.Val)
		}
	}

	return res, nil
}

func (c *Domain) collectDomainPorts(id string) (DomainPorts, error) {
	c.sshMux.Lock()
	defer c.sshMux.Unlock()

	sess, err := c.sshConn.NewSession()
	if err != nil {
		return DomainPorts{}, fmt.Errorf("create ssh session: %w", err)
	}
	defer sess.Close()

	b, err := sess.CombinedOutput(fmt.Sprintf(`cat /var/log/libvirt/qemu/%s.log | grep -e tls-port -e websocket | tail -n 2`, id))
	if err != nil {
		return DomainPorts{}, fmt.Errorf("collect domain ports: %w: %s", err, b)
	}

	ports := DomainPorts{}

	// split the different options
	for _, s := range strings.Split(strings.Replace(string(b), "\\\n", ",", -1), ",") {
		// split the key and value
		opts := strings.Split(s, "=")
		if len(opts) == 2 {
			switch opts[0] {
			case "-spice port":
				i, err := strconv.Atoi(opts[1])
				if err != nil {
					return DomainPorts{}, fmt.Errorf("convert '%s' to number: %w", opts[1], err)
				}

				ports.spice = i

			case "tls-port":
				i, err := strconv.Atoi(opts[1])
				if err != nil {
					return DomainPorts{}, fmt.Errorf("convert '%s' to number: %w", opts[1], err)
				}

				ports.spiceTls = i

			case "websocket":
				i, err := strconv.Atoi(opts[1])
				if err != nil {
					return DomainPorts{}, fmt.Errorf("convert '%s' to number: %w", opts[1], err)
				}

				ports.vncWebsocket = i
			default:
			}
		}

		if strings.HasPrefix(s, "-vnc ") {
			_, port, err := net.SplitHostPort(strings.TrimPrefix(s, "-vnc "))
			if err != nil {
				return DomainPorts{}, fmt.Errorf("parse VNC port: %w", err)
			}

			i, err := strconv.Atoi(port)
			if err != nil {
				return DomainPorts{}, fmt.Errorf("convert '%s' to number: %w", port, err)
			}

			ports.vnc = viewersBasePort + i
		}
	}

	return ports, nil
}

func (c *Domain) collectDomainMetadata(d *libvirt.Domain) (*libvirtxml.Domain, *IsardMetadata, error) {
	c.libvirtMux.Lock()
	defer c.libvirtMux.Unlock()

	raw, err := d.GetXMLDesc(0)
	if err != nil {
		return nil, nil, fmt.Errorf("get domain XML: %w", err)
	}

	domXML := &libvirtxml.Domain{}
	if err := xml.Unmarshal([]byte(raw), &domXML); err != nil {
		return nil, nil, fmt.Errorf("unmarshal domain XML: %w", err)
	}

	metadata, err := parseIsardMetadata(domXML.Metadata)
	if err != nil {
		return domXML, nil, err
	}

	return domXML, metadata, nil
}

func parseIsardMetadata(m *libvirtxml.DomainMetadata) (*IsardMetadata, error) {
	res := &metadata{}
	if err := xml.Unmarshal([]byte("<metadata>\n"+m.XML+"\n</metadata>"), res); err != nil {
		return nil, fmt.Errorf("parse Isard metadata: %w", err)
	}

	return res.IsardMetadata, nil
}

func splitDomainsIntoBatches(doms []*libvirt.Domain) [][]*libvirt.Domain {
	batches := [][]*libvirt.Domain{}
	for domainBatchSize < len(doms) {
		batches = append(batches, doms[0:domainBatchSize])
		doms = doms[domainBatchSize:]
	}

	if len(doms) != 0 {
		// Add the last (incomplete) batch
		batches = append(batches, doms[0:])
	}

	return batches
}

func genCacheID(d *libvirt.Domain) ([2]string, error) {
	id, err := d.GetID()
	if err != nil {
		return [2]string{}, fmt.Errorf("get domain ID: %w", err)
	}

	name, err := d.GetName()
	if err != nil {
		return [2]string{}, fmt.Errorf("get domain name: %w", err)
	}

	return [2]string{name, strconv.Itoa(int(id))}, nil

}

func getNameFromCacheID(id [2]string) string {
	return id[0]
}
