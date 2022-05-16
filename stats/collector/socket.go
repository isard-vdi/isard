package collector

import (
	"fmt"
	"strconv"
	"strings"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/stats/cfg"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
	"golang.org/x/crypto/ssh"
)

type Socket struct {
	mux    *sync.Mutex
	domain string
	Log    *zerolog.Logger
	conn   *ssh.Client

	descScrapeDuration *prometheus.Desc
	descScrapeSuccess  *prometheus.Desc
	descSent           *prometheus.Desc
	descRecv           *prometheus.Desc
}

func NewSocket(mux *sync.Mutex, cfg cfg.Cfg, log *zerolog.Logger, conn *ssh.Client) *Socket {
	s := &Socket{
		mux:    mux,
		domain: cfg.Domain,
		Log:    log,
		conn:   conn,
	}

	s.descScrapeDuration = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, s.String(), "scrape_duration_seconds"),
		"node_exporter: Duration of a collector scrape",
		[]string{},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	s.descScrapeSuccess = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, s.String(), "scrape_duration_success"),
		"node_exporter: Whether a collector succeed",
		[]string{},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	s.descSent = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, s.String(), "sent_bytes"),
		"Bytes sent",
		[]string{"port"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)
	s.descRecv = prometheus.NewDesc(
		prometheus.BuildFQName(namespace, s.String(), "recv_bytes"),
		"Bytes recieved",
		[]string{"port"},
		prometheus.Labels{
			"hypervisor": cfg.Domain,
		},
	)

	return s
}

func (s *Socket) String() string {
	return "socket"
}

func (s *Socket) Describe(ch chan<- *prometheus.Desc) {
	ch <- s.descScrapeDuration
	ch <- s.descScrapeSuccess
	ch <- s.descSent
	ch <- s.descRecv
}

func (s *Socket) Collect(ch chan<- prometheus.Metric) {
	start := time.Now()

	success := 1
	viewers, err := s.collectViewers()
	if err != nil {
		s.Log.Info().Str("collector", s.String()).Err(err).Msg("collect viewers")
		success = 0
	}

	for src, v := range viewers {
		port := strconv.Itoa(src)
		ch <- prometheus.MustNewConstMetric(s.descSent, prometheus.GaugeValue, float64(v.Sent), port)
		ch <- prometheus.MustNewConstMetric(s.descRecv, prometheus.GaugeValue, float64(v.Recv), port)
	}

	duration := time.Since(start)

	ch <- prometheus.MustNewConstMetric(s.descScrapeDuration, prometheus.GaugeValue, duration.Seconds())
	ch <- prometheus.MustNewConstMetric(s.descScrapeSuccess, prometheus.GaugeValue, float64(success))

}

type viewer struct {
	DstPorts      []int
	PID           int
	SentByDstPort []int
	RecvByDstPort []int
	Sent          int
	Recv          int
}

func (s *Socket) collectViewers() (map[int]*viewer, error) {
	s.mux.Lock()
	defer s.mux.Unlock()

	sess, err := s.conn.NewSession()
	if err != nil {
		return nil, fmt.Errorf("create ssh session: %w", err)
	}
	defer sess.Close()

	// TODO: 5700 for websocket ports?
	b, err := sess.CombinedOutput(`ss -t state established -o state established -t -n -p -i "( sport > 5900 )" -O`)
	if err != nil {
		return nil, fmt.Errorf("collect viewers: %w", err)
	}

	viewers := map[int]*viewer{}
	lines := strings.Split(string(b), "\n")

	for i, line := range lines {
		if strings.Contains(line, "qemu") {
			split := strings.Split(line, ":")

			src, err := strconv.Atoi(strings.Split(split[1], " ")[0])
			if err != nil {
				return map[int]*viewer{}, fmt.Errorf("parse source port: %w", err)
			}

			dst, err := strconv.Atoi(strings.Split(split[2], " ")[0])
			if err != nil {
				return map[int]*viewer{}, fmt.Errorf("parse destination port: %w", err)
			}

			var (
				sent, recv int
			)

			bAcked := strings.Split(lines[i], "bytes_acked:")
			if len(bAcked) > 1 {
				sent, err = strconv.Atoi(strings.Split(bAcked[1], " ")[0])
				if err != nil {
					return map[int]*viewer{}, fmt.Errorf("parse bytes sent: %w", err)
				}

				recv, err = strconv.Atoi(strings.Split(strings.Split(lines[i], "bytes_received:")[1], " ")[0])
				if err != nil {
					return map[int]*viewer{}, fmt.Errorf("parse bytes received: %w", err)
				}
			}

			pid, err := strconv.Atoi(strings.Split(strings.Split(line, "pid=")[1], ",")[0])
			if err != nil {
				return map[int]*viewer{}, fmt.Errorf("parse pid: %w", err)
			}

			if v, ok := viewers[src]; !ok {
				viewers[src] = &viewer{
					DstPorts:      []int{},
					PID:           pid,
					SentByDstPort: []int{},
					RecvByDstPort: []int{},
					Sent:          0,
					Recv:          0,
				}

			} else {
				v.DstPorts = append(v.DstPorts, dst)
				v.SentByDstPort = append(v.SentByDstPort, sent)
				v.RecvByDstPort = append(v.RecvByDstPort, recv)
				v.Sent += sent
				v.Recv += recv
			}
		}
	}

	return viewers, nil
}
