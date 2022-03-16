package collector

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/stats/cfg"

	"github.com/influxdata/influxdb-client-go/v2/api/write"
	"golang.org/x/crypto/ssh"
	"libvirt.org/go/libvirt"
)

type Domain struct {
	hyp         string
	libvirtMux  *sync.Mutex
	libvirtConn *libvirt.Connect
	sshMux      *sync.Mutex
	sshConn     *ssh.Client
}

func NewDomain(libvirtMux *sync.Mutex, sshMux *sync.Mutex, cfg cfg.Cfg, libvirtConn *libvirt.Connect, sshConn *ssh.Client) *Domain {
	return &Domain{
		libvirtMux:  libvirtMux,
		libvirtConn: libvirtConn,
		sshMux:      sshMux,
		sshConn:     sshConn,
		hyp:         cfg.Domain,
	}
}

func (d *Domain) String() string {
	return "domain"
}

func (d *Domain) Close() error {
	return nil
}

func (d *Domain) Collect(ctx context.Context) ([]*write.Point, error) {
	start := time.Now()

	stats, err := d.collectStats()
	if err != nil {
		// TODO: Should we return? Or just log the error and go on?
		return nil, err
	}

	points := []*write.Point{}
	for _, s := range stats {
		d.libvirtMux.Lock()
		id, err := s.Domain.GetName()
		if err != nil {
			// TODO: Should we return? Or just log the error and go on?
			return nil, fmt.Errorf("get the domain name: %w", err)
		}
		d.libvirtMux.Unlock()

		defer func() {
			d.libvirtMux.Lock()
			defer d.libvirtMux.Unlock()

			s.Domain.Free()
		}()

		mem, err := d.collectMemStats(s.Domain)
		if err != nil {
			return nil, err
		}

		ports, err := d.collectDomainPorts(id)
		if err != nil {
			// TODO: Should we return? Or just log the error and go on?
			return nil, err
		}

		points = append(points, write.NewPoint(d.String(), map[string]string{
			"hypervisor": d.hyp,
			"id":         id,
		}, ports, start))

		p, err := transformLibvirtData(start, d.String(), map[string]string{
			"hypervisor": d.hyp,
			"id":         id,
		}, "", map[string]interface{}{
			"cpuSet":         s.Cpu != nil,
			"cpu":            s.Cpu,
			"balloonSet":     s.Balloon != nil,
			"balloon":        s.Balloon,
			"vcpuSet":        s.Vcpu != nil,
			"vcpu":           s.Vcpu,
			"vcpuCurrentSet": true,
			"vcpuCurrent":    len(s.Vcpu),
			"netSet":         s.Net != nil,
			"net":            s.Net,
			"blockSet":       s.Block != nil,
			"block":          s.Block,
			"perfSet":        s.Perf != nil,
			"perf":           s.Perf,
			"memSet":         true,
			"mem":            mem,
			"dirty_rateSet":  s.DirtyRate != nil,
			"dirty_rate":     s.DirtyRate,
		})
		if err != nil {
			// TODO: Should we return? Or just log the error and go on?
			return nil, fmt.Errorf("transform libvirt data: %w", err)
		}

		points = append(points, p...)
	}

	return points, nil
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

func (d *Domain) collectMemStats(dom *libvirt.Domain) (map[string]interface{}, error) {
	d.libvirtMux.Lock()
	defer d.libvirtMux.Unlock()

	mem, err := dom.MemoryStats(uint32(libvirt.DOMAIN_MEMORY_STAT_NR), 0)
	if err != nil {
		return nil, fmt.Errorf("get the domain memory stats: %w", err)
	}

	res := map[string]interface{}{}
	for _, m := range mem {
		switch m.Tag {
		case int32(libvirt.DOMAIN_MEMORY_STAT_UNUSED):
			res["available"] = m.Val
			res["availableSet"] = true

		case int32(libvirt.DOMAIN_MEMORY_STAT_AVAILABLE):
			res["total"] = m.Val
			res["totalSet"] = true
		}
	}

	return res, nil
}

func (d *Domain) collectDomainPorts(id string) (map[string]interface{}, error) {
	d.sshMux.Lock()
	defer d.sshMux.Unlock()

	sess, err := d.sshConn.NewSession()
	if err != nil {
		return nil, fmt.Errorf("create ssh session: %w", err)
	}
	defer sess.Close()

	b, err := sess.CombinedOutput(fmt.Sprintf(`cat /var/log/libvirt/qemu/%s.log | grep -e tls-port -e websocket | tail -n 2 | awk '{ print $2 }'`, id))
	if err != nil {
		return nil, fmt.Errorf("collect domain ports: %w: %s", err, b)
	}

	ports := map[string]interface{}{}

	// split the different options
	for _, s := range strings.Split(string(b), ",") {
		// split the key and value
		opts := strings.Split(s, "=")
		if len(opts) == 2 {
			switch opts[0] {
			case "port":
				ports["viewer_port_spice"] = opts[1]

			case "tls-port":
				ports["viewer_port_spice_tls"] = opts[1]

			case "websocket":
				ports["viewer_port_websocket"] = opts[1]
			default:
			}
		}
	}

	return ports, nil
}
