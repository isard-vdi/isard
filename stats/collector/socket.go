package collector

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/influxdata/influxdb-client-go/v2/api/write"
	"gitlab.com/isard/isardvdi/stats/cfg"
	"golang.org/x/crypto/ssh"
)

type Socket struct {
	mux    *sync.Mutex
	domain string
	conn   *ssh.Client
}

func NewSocket(mux *sync.Mutex, cfg cfg.Cfg, conn *ssh.Client) *Socket {
	return &Socket{
		mux:    mux,
		domain: cfg.Domain,
		conn:   conn,
	}
}

func (s *Socket) String() string {
	return "socket"
}

func (s *Socket) Close() error {
	return nil
}

func (s *Socket) Collect(ctx context.Context) ([]*write.Point, error) {
	start := time.Now()

	viewers, err := s.collectViewers()
	if err != nil {
		return nil, err
	}

	points := []*write.Point{}
	for src, v := range viewers {
		points = append(points, write.NewPoint(
			s.String(),
			map[string]string{
				"hypervisor":  s.domain,
				"source_port": strconv.Itoa(src),
			},
			map[string]interface{}{
				"destination_ports":             v.DstPorts,
				"pid":                           v.PID,
				"sent_by_destination_ports":     v.SentByDstPort,
				"recieved_by_destination_ports": v.RecvByDstPort,
				"sent":                          v.Sent,
				"recieved":                      v.Recv,
			},
			start,
		))
	}

	return points, nil
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
	b, err := sess.CombinedOutput(`ss -t state established -o state established -t -n -p -i "( sport > 5900 )"`)
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

			sent, err := strconv.Atoi(strings.Split(strings.Split(lines[i+1], "bytes_acked:")[1], " ")[0])
			if err != nil {
				return map[int]*viewer{}, fmt.Errorf("parse bytes sent: %w", err)
			}

			recv, err := strconv.Atoi(strings.Split(strings.Split(lines[i+1], "bytes_received:")[1], " ")[0])
			if err != nil {
				return map[int]*viewer{}, fmt.Errorf("parse bytes received: %w", err)
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
