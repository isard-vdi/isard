package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/stats/cfg"
	"gitlab.com/isard/isardvdi/stats/collector"

	influxdb2 "github.com/influxdata/influxdb-client-go/v2"
	"golang.org/x/crypto/ssh"
	"golang.org/x/crypto/ssh/knownhosts"
	"libvirt.org/go/libvirt"
)

// TODO: Improve logging

func main() {
	cfg := cfg.New()

	log := log.New("stats", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())

	var sshConn *ssh.Client
	var sshMux sync.Mutex
	if cfg.Collectors.Socket.Enable || cfg.Collectors.Domain.Enable {
		kHosts, err := knownhosts.New(filepath.Join(os.Getenv("HOME"), ".ssh", "known_hosts"))
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("read known hosts")
		}

		b, err := os.ReadFile(filepath.Join(os.Getenv("HOME"), ".ssh", "id_rsa"))
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("read private key")
		}

		pKey, err := ssh.ParsePrivateKey(b)
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("parse private key")
		}

		sshCfg := &ssh.ClientConfig{
			User: cfg.SSH.User,
			Auth: []ssh.AuthMethod{
				ssh.PublicKeys(pKey),
			},
			HostKeyCallback: kHosts,
		}

		sshConn, err = ssh.Dial("tcp", fmt.Sprintf("%s:%d", cfg.SSH.Host, cfg.SSH.Port), sshCfg)
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("connect using SSH")
		}
	}

	var libvirtConn *libvirt.Connect
	var libvirtMux sync.Mutex
	if cfg.Collectors.Hypervisor.Enable || cfg.Collectors.Domain.Enable {
		// TODO: We should add a libvirt timeout
		var err error
		libvirtConn, err = libvirt.NewConnectReadOnly(cfg.LibvirtURI)
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("connect to libvirt")
		}

		alive, err := libvirtConn.IsAlive()
		if err != nil || !alive {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("connection not alive")
		}
	}

	collectors := map[string]collector.Collector{}

	if cfg.Collectors.Hypervisor.Enable {
		h := collector.NewHypervisor(&libvirtMux, cfg, libvirtConn)
		collectors[h.String()] = h
	}

	if cfg.Collectors.Domain.Enable {
		d := collector.NewDomain(&libvirtMux, &sshMux, cfg, libvirtConn, sshConn)
		collectors[d.String()] = d
	}

	if cfg.Collectors.System.Enable {
		s := collector.NewSystem(cfg)
		collectors[s.String()] = s
	}

	if cfg.Collectors.Socket.Enable {
		s := collector.NewSocket(&sshMux, cfg, sshConn)
		collectors[s.String()] = s
	}

	enabledCollectors := []string{}
	for k := range collectors {
		enabledCollectors = append(enabledCollectors, k)
	}

	client := influxdb2.NewClient(cfg.InfluxDB.Address, cfg.InfluxDB.Token)
	defer client.Close()

	write := client.WriteAPIBlocking(cfg.InfluxDB.Org, cfg.InfluxDB.Bucket)

	go func() {
		for {
			for name, c := range collectors {
				p, err := c.Collect(ctx)
				if err != nil {
					log.Error().Err(err).Msgf("collect data from %s", name)
					continue
				}

				if err := write.WritePoint(ctx, p...); err != nil {
					log.Error().Err(err).Msgf("insert data into InfluxDB from %s", name)
					continue
				}

				log.Info().Str("collector", name).Interface("point", &p).Msg("data sent")
			}

			time.Sleep(time.Second)
		}
	}()

	log.Info().Strs("collectors", enabledCollectors).Msg("service started")

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()

	for _, c := range collectors {
		c.Close()
	}

	if libvirtConn != nil {
		libvirtConn.Close()
	}

	if sshConn != nil {
		sshConn.Close()
	}
}
