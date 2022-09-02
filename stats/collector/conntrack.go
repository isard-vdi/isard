package collector

import (
	"bytes"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"os"
	"strconv"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
)

type Conntrack struct {
	Log *zerolog.Logger

	descScrapeDuration *prometheus.Desc
	descScrapeSuccess  *prometheus.Desc
	descRDPSent        *prometheus.Desc
	descRDPRecv        *prometheus.Desc
}

func NewConntrack(log *zerolog.Logger) *Conntrack {
	c := &Conntrack{
		Log: log,
	}

	c.descScrapeDuration = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, c.String(), "scrape_duration_seconds"),
		"node_exporter: Duration of a collector scrape",
		[]string{},
		prometheus.Labels{},
	)
	c.descScrapeSuccess = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, c.String(), "scrape_duration_success"),
		"node_exporter: Whether a collector succeed",
		[]string{},
		prometheus.Labels{},
	)
	c.descRDPSent = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, c.String(), "rdp_sent_bytes"),
		"RDP bytes sent",
		[]string{"ip", "mac", "port"},
		prometheus.Labels{},
	)
	c.descRDPRecv = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, c.String(), "rdp_recv_bytes"),
		"RDP bytes recieved",
		[]string{"ip", "mac", "port"},
		prometheus.Labels{},
	)

	return c
}

func (c *Conntrack) String() string {
	return "conntrack"
}

func (c *Conntrack) Describe(ch chan<- *prometheus.Desc) {
	ch <- c.descScrapeDuration
	ch <- c.descScrapeSuccess
	ch <- c.descRDPSent
	ch <- c.descRDPRecv
}

func (c *Conntrack) Collect(ch chan<- prometheus.Metric) {
	start := time.Now()

	success := 1

	rdp, err := c.collectRDP()
	if err != nil {
		c.Log.Info().Str("collector", c.String()).Err(err).Msg("collect RDP")
		success = 0
	}

	for _, r := range rdp {
		ch <- prometheus.MustNewConstMetric(c.descRDPSent, prometheus.GaugeValue, float64(r.Sent), r.Host, r.Mac, strconv.Itoa(r.Port))
		ch <- prometheus.MustNewConstMetric(c.descRDPRecv, prometheus.GaugeValue, float64(r.Recv), r.Host, r.Mac, strconv.Itoa(r.Port))
	}

	duration := time.Since(start)

	ch <- prometheus.MustNewConstMetric(c.descScrapeDuration, prometheus.GaugeValue, duration.Seconds())
	ch <- prometheus.MustNewConstMetric(c.descScrapeSuccess, prometheus.GaugeValue, float64(success))
}

type rdp struct {
	Host string
	Mac  string
	Port int
	Sent int
	Recv int
}

type conntrackXML struct {
	XMLName xml.Name `xml:"conntrack"`
	Flow    []struct {
		XMLName xml.Name `xml:"flow"`
		Meta    []struct {
			XMLName   xml.Name `xml:"meta"`
			Direction string   `xml:"direction,attr"`
			Content   []byte   `xml:",innerxml"`
		} `xml:"meta"`
	} `xml:"flow"`
}

type conntrackXMLMetaDirectionGeneric struct {
	XMLName xml.Name `xml:"meta"`
	Layer3  struct {
		XMLName   xml.Name `xml:"layer3"`
		Protonum  int      `xml:"protonum,attr"`
		Protoname string   `xml:"protoname"`
		Src       string   `xml:"src"`
		Dst       string   `xml:"dst"`
	} `xml:"layer3"`
	Layer4 struct {
		XMLName   xml.Name `xml:"layer4"`
		Protonum  int      `xml:"protonum,attr"`
		Protoname string   `xml:"protoname"`
		Sport     int      `xml:"sport"`
		Dport     int      `xml:"dport"`
	} `xml:"layer4"`
	Counters struct {
		XMLName xml.Name `xml:"counters"`
		Packets int      `xml:"packets"`
		Bytes   int      `xml:"bytes"`
	} `xml:"counters"`
}

type conntrackXMLMetaDirectionIndependent struct {
	XMLName xml.Name `xml:"meta"`
	State   string   `xml:"state"`
}

type arpJSON struct {
	Dst    string `json:"dst"`
	LlAddr string `json:"lladdr"`
}

func (c *Conntrack) collectRDP() ([]*rdp, error) {
	bConn, err := os.ReadFile("/conntrack/rdp.xml")
	if err != nil {
		return nil, fmt.Errorf("read RDP conntrack file: %w", err)
	}

	if bytes.Equal(bConn, nil) {
		return []*rdp{}, nil
	}

	connXML := &conntrackXML{}
	if err := xml.Unmarshal(bConn, connXML); err != nil {
		return nil, fmt.Errorf("unmarshal RDP XML: %w", err)
	}

	rsp := []*rdp{}

flow:
	for _, f := range connXML.Flow {
		r := &rdp{}
		for _, m := range f.Meta {
			// dirty hack in order to parse elements without a root
			content := []byte(fmt.Sprintf("<meta>%s</meta>", m.Content))

			switch m.Direction {
			case "original", "reply":
				g := &conntrackXMLMetaDirectionGeneric{}
				if err := xml.Unmarshal(content, g); err != nil {
					return nil, fmt.Errorf("unmarshal RDP XML direction %s: %w", m.Direction, err)
				}

				if m.Direction == "original" {
					r.Host = g.Layer3.Dst
					r.Port = g.Layer4.Dport
					r.Recv = g.Counters.Bytes
				} else {
					r.Sent = g.Counters.Bytes
				}

			case "independent":
				i := &conntrackXMLMetaDirectionIndependent{}
				if err := xml.Unmarshal(content, i); err != nil {
					return nil, fmt.Errorf("unmarshal RDP XML direction independent: %w", err)
				}

				if i.State != "ESTABLISHED" {
					continue flow
				}

			default:
				return nil, fmt.Errorf("unmarshal RDP XML: invalid direction: %s", m.Direction)
			}
		}

		rsp = append(rsp, r)
	}

	bArp, err := os.ReadFile("/conntrack/arp.json")
	if err != nil {
		return nil, fmt.Errorf("read RDP arp file: %w", err)
	}

	arp := []*arpJSON{}

	if err := json.Unmarshal(bArp, &arp); err != nil {
		return nil, fmt.Errorf("unmarshal RDP ARP: %w", err)
	}

	neigh := map[string]string{}
	for _, a := range arp {
		neigh[a.Dst] = a.LlAddr
	}

	for _, r := range rsp {
		mac, ok := neigh[r.Host]
		if ok {
			r.Mac = mac
		}
	}

	return rsp, nil
}
