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

	lokiCli "github.com/grafana/loki/v3/pkg/logcli/client"
	"github.com/oracle/oci-go-sdk/v65/common"
	"github.com/oracle/oci-go-sdk/v65/usageapi"
	"github.com/rs/zerolog"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
	"golang.org/x/crypto/ssh"
)

func main() {
	cfg := cfg.New()

	log := log.New("stats", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	collectors, libvirtPool, sshPool := startCollectors(ctx, cfg, log)

	enabledCollectors := []string{}
	for _, c := range collectors {
		enabledCollectors = append(enabledCollectors, c.String())
	}

	http := &http.StatsServer{
		Addr:       cfg.HTTP.Addr(),
		Log:        log,
		Collectors: collectors,
	}

	wg.Go(func() {
		http.Serve(ctx, log)
	})

	log.Info().Strs("collectors", enabledCollectors).Msg("service started")

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt)

	<-stop
	fmt.Println("")
	log.Info().Msg("stopping service")

	cancel()
	wg.Wait()

	if libvirtPool != nil {
		libvirtPool.Close()
	}

	if sshPool != nil {
		sshPool.Close()
	}
}

func hasHypervisor(flavour string) bool {
	switch flavour {
	case "all-in-one", "hypervisor", "hypervisor-standalone":
		return true
	default:
		return false
	}
}

func hasWeb(flavour string) bool {
	switch flavour {
	case "all-in-one", "web", "web+monitor", "web+storage+monitor", "web+storage+video+monitor":
		return true
	default:
		return false
	}
}

func startCollectors(ctx context.Context, cfg cfg.Cfg, log *zerolog.Logger) ([]collector.Collector, *collector.LibvirtPool, *collector.SSHPool) {
	domain := hasHypervisor(cfg.Flavour) && cfg.Collectors.Domain.Enable
	hypervisor := hasHypervisor(cfg.Flavour) && cfg.Collectors.Hypervisor.Enable
	socket := hasHypervisor(cfg.Flavour) && cfg.Collectors.Socket.Enable
	system := cfg.Collectors.System.Enable
	isardvdiAPI := hasWeb(cfg.Flavour) && cfg.Collectors.IsardVDIAPI.Enable
	isardvdiAuthentication := hasWeb(cfg.Flavour) && cfg.Collectors.IsardVDIAuthentication.Enable
	storageGovernor := hasWeb(cfg.Flavour)
	oci := hasWeb(cfg.Flavour) && cfg.Collectors.OCI.Enable
	conntrack := hasWeb(cfg.Flavour) && cfg.Collectors.Conntrack.Enable

	var sshPool *collector.SSHPool
	if domain || socket {
		hostKeyCB, err := collector.NewSelfHealingHostKeyCallback(filepath.Join(os.Getenv("HOME"), ".ssh", "known_hosts"), log)
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
			HostKeyCallback: hostKeyCB,
		}

		sshPool, err = collector.NewSSHPool(fmt.Sprintf("%s:%d", cfg.SSH.Host, cfg.SSH.Port), sshCfg, log)
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Str("host", cfg.SSH.Host).Int("port", cfg.SSH.Port).Msg("connect using SSH")
		}
	}

	var libvirtPool *collector.LibvirtPool
	if hypervisor || domain {
		// TODO: We should add a libvirt timeout
		var err error
		libvirtPool, err = collector.NewLibvirtPool(cfg.LibvirtURI, log)
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("connect to libvirt")
		}
	}

	collectors := []collector.Collector{}

	if system {
		s := collector.NewSystem(cfg, log)
		collectors = append(collectors, s)
	}

	if hypervisor {
		h := collector.NewHypervisor(cfg, log, libvirtPool)
		collectors = append(collectors, h)
	}

	if domain {
		d := collector.NewDomain(ctx, cfg, log, libvirtPool, sshPool)
		collectors = append(collectors, d)
	}

	if socket {
		s := collector.NewSocket(cfg, log, sshPool)
		collectors = append(collectors, s)
	}

	if isardvdiAPI {
		httpClient := ogenclient.NewHTTPClient(ogenclient.WithIgnoreCerts())
		cli, err := apiv4.NewClient(
			cfg.Collectors.IsardVDIAPI.Addr,
			ogenclient.APIv4Source{Secret: cfg.Collectors.IsardVDIAPI.Secret},
			apiv4.WithClient(httpClient),
		)
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("create API client")
		}

		a := collector.NewIsardVDIAPI(ctx, log, cli)
		collectors = append(collectors, a)
	}

	if storageGovernor {
		httpClient := ogenclient.NewHTTPClient(ogenclient.WithIgnoreCerts())
		cli, err := apiv4.NewClient(
			cfg.Collectors.IsardVDIAPI.Addr,
			ogenclient.APIv4Source{Secret: cfg.Collectors.IsardVDIAPI.Secret},
			apiv4.WithClient(httpClient),
		)
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("create storage governor API client")
		}

		g := collector.NewStorageGovernor(ctx, log, cli)
		collectors = append(collectors, g)
	}

	if isardvdiAuthentication {
		cli := &lokiCli.DefaultClient{Address: cfg.Collectors.IsardVDIAuthentication.LokiAddress}
		a := collector.NewIsardVDIAuthentication(log, cli)
		collectors = append(collectors, a)
	}

	if oci {
		cli, err := usageapi.NewUsageapiClientWithConfigurationProvider(common.DefaultConfigProvider())
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("create OCI usage client")
		}

		cliCfg := *cli.ConfigurationProvider()
		tenancy, err := cliCfg.TenancyOCID()
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("get OCI client tenancy")
		}

		o := collector.NewOCI(log, cli, tenancy)
		collectors = append(collectors, o)
	}

	if conntrack {
		c := collector.NewConntrack(log)
		collectors = append(collectors, c)
	}

	return collectors, libvirtPool, sshPool
}
