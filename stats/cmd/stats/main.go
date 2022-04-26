package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"sync"

	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/stats/cfg"
	"gitlab.com/isard/isardvdi/stats/collector"
	"gitlab.com/isard/isardvdi/stats/transport/http"

	"golang.org/x/crypto/ssh"
	"golang.org/x/crypto/ssh/knownhosts"
	"libvirt.org/go/libvirt"
)

// TODO: Improve logging

func main() {
	cfg := cfg.New()

	log := log.New("stats", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

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
			log.Fatal().Err(err).Str("domain", cfg.Domain).Str("host", cfg.SSH.Host).Int("port", cfg.SSH.Port).Msg("connect using SSH")
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

	collectors := []collector.Collector{}

	if cfg.Collectors.Hypervisor.Enable {
		h := collector.NewHypervisor(&libvirtMux, cfg, log, libvirtConn)
		collectors = append(collectors, h)
	}

	if cfg.Collectors.Domain.Enable {
		d := collector.NewDomain(&libvirtMux, &sshMux, cfg, log, libvirtConn, sshConn)
		collectors = append(collectors, d)
	}

	if cfg.Collectors.System.Enable {
		s := collector.NewSystem(cfg, log)
		collectors = append(collectors, s)
	}

	if cfg.Collectors.Socket.Enable {
		s := collector.NewSocket(&sshMux, cfg, log, sshConn)
		collectors = append(collectors, s)
	}

	enabledCollectors := []string{}
	for _, c := range collectors {
		enabledCollectors = append(enabledCollectors, c.String())
	}

	http := &http.StatsServer{
		Addr:       cfg.HTTP.Addr(),
		Log:        log,
		WG:         &wg,
		Collectors: collectors,
	}

	go http.Serve(ctx)
	wg.Add(1)

	log.Info().Strs("collectors", enabledCollectors).Msg("service started")

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()

	if libvirtConn != nil {
		libvirtConn.Close()
	}

	if sshConn != nil {
		sshConn.Close()
	}
}
