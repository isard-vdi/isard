package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"sync"

	"gitlab.com/isard/isardvdi/pkg/jwt"
	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/stats/cfg"
	"gitlab.com/isard/isardvdi/stats/collector"
	"gitlab.com/isard/isardvdi/stats/transport/http"

	lokiCli "github.com/grafana/loki/v3/pkg/logcli/client"
	"github.com/oracle/oci-go-sdk/v65/common"
	"github.com/oracle/oci-go-sdk/v65/usageapi"
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi/pkg/sdk"
	"golang.org/x/crypto/ssh"
	"golang.org/x/crypto/ssh/knownhosts"
	"libvirt.org/go/libvirt"
)

func main() {
	cfg := cfg.New()

	log := log.New("stats", cfg.Log.Level)

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup

	collectors, libvirtConn, sshConn := startCollectors(ctx, cfg, log)

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

	go http.Serve(ctx, log)
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
	case "all-in-one", "web":
		return true
	default:
		return false
	}
}

func startCollectors(ctx context.Context, cfg cfg.Cfg, log *zerolog.Logger) ([]collector.Collector, *libvirt.Connect, *ssh.Client) {
	domain := hasHypervisor(cfg.Flavour) && cfg.Collectors.Domain.Enable
	hypervisor := hasHypervisor(cfg.Flavour) && cfg.Collectors.Hypervisor.Enable
	socket := hasHypervisor(cfg.Flavour) && cfg.Collectors.Socket.Enable
	system := cfg.Collectors.System.Enable
	isardvdiAPI := hasWeb(cfg.Flavour) && cfg.Collectors.IsardVDIAPI.Enable
	isardvdiAuthentication := hasWeb(cfg.Flavour) && cfg.Collectors.IsardVDIAuthentication.Enable
	oci := hasWeb(cfg.Flavour) && cfg.Collectors.OCI.Enable
	conntrack := hasWeb(cfg.Flavour) && cfg.Collectors.Conntrack.Enable

	var sshConn *ssh.Client
	var sshMux sync.Mutex
	if domain || socket {
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
	if hypervisor || domain {
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

	if system {
		s := collector.NewSystem(cfg, log)
		collectors = append(collectors, s)
	}

	if hypervisor {
		h := collector.NewHypervisor(&libvirtMux, cfg, log, libvirtConn)
		collectors = append(collectors, h)
	}

	if domain {
		d := collector.NewDomain(ctx, &libvirtMux, &sshMux, cfg, log, libvirtConn, sshConn)
		collectors = append(collectors, d)
	}

	if socket {
		s := collector.NewSocket(&sshMux, cfg, log, sshConn)
		collectors = append(collectors, s)
	}

	if isardvdiAPI {
		cli, err := sdk.NewClient(&sdk.Cfg{
			Host:        cfg.Collectors.IsardVDIAPI.Addr,
			IgnoreCerts: true,
		})
		if err != nil {
			log.Fatal().Err(err).Str("domain", cfg.Domain).Msg("create API client")
		}

		cli.SetBeforeRequestHook(func(c *sdk.Client) error {
			tkn, err := jwt.SignAPIJWT(cfg.Collectors.IsardVDIAPI.Secret)
			if err != nil {
				return fmt.Errorf("sign JWT token for calling the API: %w", err)
			}

			c.SetToken(tkn)

			return nil
		})

		a := collector.NewIsardVDIAPI(log, cli)
		collectors = append(collectors, a)
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

	return collectors, libvirtConn, sshConn
}
