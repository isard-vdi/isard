package check

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os/exec"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog"
	"github.com/teris-io/shortid"
	"gitlab.com/isard/isardvdi/check/cfg"
	"gitlab.com/isard/isardvdi/pkg/sdk"
	sshExec "gitlab.com/isard/isardvdi/pkg/ssh"
	"golang.org/x/crypto/ssh"
)

const (
	desktopTimeout = 90
	sshUser        = "executor"
)

var ErrMaintenanceMode = errors.New("maintenance mode is activated")

type Interface interface {
	CheckIsardVDI(ctx context.Context, authMethod AuthMethod, auth Auth, host, templateID string, failSelfSigned, failMaintenance bool) (CheckResult, error)
	CheckHypervisor(ctx context.Context, authMethod AuthMethod, auth Auth, host, hyperID, templateID string, failSelfSigned, failMaintenance bool) (CheckResult, error)
}

type CheckResult struct {
	IsardVDIVersion      string
	MaintenanceMode      bool
	DependenciesVersions DependenciesVersions
	HypervisorNum        int
}

type DependenciesVersions struct {
	Remmina      string
	RemoteViewer string
	WireGuard    string
}

type Check struct {
	log *zerolog.Logger
	cfg cfg.Check
}

func NewCheck(cfg cfg.Check, log *zerolog.Logger) *Check {
	return &Check{log, cfg}
}

func (c *Check) CheckIsardVDI(ctx context.Context, authMethod AuthMethod, auth Auth, host, templateID string, failSelfSigned, failMaintenance bool) (CheckResult, error) {
	cli, err := sdk.NewClient(&sdk.Cfg{
		Host:        host,
		IgnoreCerts: !failSelfSigned,
	})
	if err != nil {
		return CheckResult{}, fmt.Errorf("create API client: %w", err)
	}

	if err := c.auth(ctx, cli, authMethod, auth); err != nil {
		return CheckResult{}, err
	}
	c.log.Debug().Msg("authenticated with api key")

	version, err := cli.Version(ctx)
	if err != nil {
		return CheckResult{}, fmt.Errorf("get IsardVDI version: %w", err)
	}

	maintenance, err := cli.Maintenance(ctx)
	if err != nil {
		return CheckResult{
			IsardVDIVersion: version,
		}, fmt.Errorf("get maintenance mode: %w", err)
	}

	if failMaintenance && maintenance {
		return CheckResult{
			IsardVDIVersion: version,
			MaintenanceMode: maintenance,
		}, ErrMaintenanceMode
	}

	h, err := cli.HypervisorList(ctx)
	if err != nil {
		return CheckResult{
			IsardVDIVersion: version,
			MaintenanceMode: maintenance,
		}, fmt.Errorf("list hypervisors: %w", err)
	}

	var wg sync.WaitGroup
	errCh := make(chan error, len(h))
	depsCh := make(chan DependenciesVersions, len(h))

	for _, hyper := range h {
		wg.Add(1)

		go func(hyper *sdk.Hypervisor) {
			defer wg.Done()

			c.log.Debug().Str("host", cli.URL().Host).Str("id", *hyper.ID).Msg("checking hypervisor")

			deps, err := c.checkHypervisor(ctx, cli, sdk.GetString(hyper.ID), templateID, failSelfSigned)
			if err != nil {
				c.log.Error().Str("host", cli.URL().Host).Str("hypervisor", sdk.GetString(hyper.ID)).Str("template_id", templateID).Err(err).Msg("check hypervisor")
				err = fmt.Errorf("check hypervisor '%s': %w", sdk.GetString(hyper.ID), err)
			}

			depsCh <- deps
			errCh <- err
		}(hyper)
	}

	// Wait for all the checks to be finished
	wg.Wait()

	// Check if there are errors and retrieve the check dependencies
	deps := DependenciesVersions{}
	for range h {
		deps = <-depsCh
		err := <-errCh

		if err != nil {
			return CheckResult{
				IsardVDIVersion:      version,
				MaintenanceMode:      maintenance,
				DependenciesVersions: deps,
				HypervisorNum:        len(h),
			}, err
		}
	}

	return CheckResult{
		IsardVDIVersion:      version,
		MaintenanceMode:      maintenance,
		DependenciesVersions: deps,
		HypervisorNum:        len(h),
	}, nil
}

func (c *Check) CheckHypervisor(ctx context.Context, authMethod AuthMethod, auth Auth, host, hyperID, templateID string, failSelfSigned, failMaintenance bool) (CheckResult, error) {
	cli, err := sdk.NewClient(&sdk.Cfg{
		Host:        host,
		IgnoreCerts: !failSelfSigned,
	})
	if err != nil {
		return CheckResult{}, fmt.Errorf("create API client: %w", err)
	}

	if err := c.auth(ctx, cli, authMethod, auth); err != nil {
		return CheckResult{}, err
	}

	version, err := cli.Version(ctx)
	if err != nil {
		return CheckResult{}, fmt.Errorf("get IsardVDI version: %w", err)
	}

	maintenance, err := cli.Maintenance(ctx)
	if err != nil {
		return CheckResult{}, fmt.Errorf("get maintenance mode: %w", err)
	}

	if failMaintenance && maintenance {
		return CheckResult{}, ErrMaintenanceMode
	}

	deps, err := c.checkHypervisor(ctx, cli, hyperID, templateID, failSelfSigned)
	if err != nil {
		c.log.Error().Str("host", cli.URL().Host).Str("hypervisor", hyperID).Str("template_id", templateID).Err(err).Msg("check hypervisor")

		return CheckResult{}, fmt.Errorf("check hypervisor: %w", err)
	}

	return CheckResult{
		IsardVDIVersion:      version,
		MaintenanceMode:      maintenance,
		DependenciesVersions: deps,
	}, nil
}

func (c *Check) prepareDocker(ctx context.Context, checkID string) (*ssh.Client, string, error) {
	out, err := exec.Command("bash", "-c", `docker inspect isard-check | jq -j '.[0].NetworkSettings.Networks | keys[0]'`).CombinedOutput()
	if err != nil {
		return nil, "", fmt.Errorf("get container network name: %w: %s", err, out)
	}
	netName := strings.TrimSpace(string(out))

	out, err = exec.Command("bash", "-c", fmt.Sprintf(`docker run -d --name "%s" --network "%s" --cap-add=NET_ADMIN -e "CHECK_MODE=client" -e "SSH_USER=%s" -e "SSH_PASSWORD=%s" %s`, checkID, netName, sshUser, checkID, c.cfg.Image)).CombinedOutput()
	if err != nil {
		return nil, "", fmt.Errorf("create check docker container: %w: %s", err, out)
	}

	dID := strings.TrimSpace(string(out))

	out, err = exec.Command("bash", "-c", fmt.Sprintf(`docker inspect %s | jq -j '.[0].NetworkSettings.Networks["%s"].IPAddress'`, checkID, netName)).CombinedOutput()
	if err != nil {
		return nil, dID, fmt.Errorf("get container IP address: %w: %s", err, out)
	}

	ip := strings.TrimSpace(string(out))

	// Wait for Dropbear to start
	timeout := time.After(30 * time.Second)
waitForSSH:
	for {
		select {
		case <-timeout:
			return nil, dID, fmt.Errorf("timeout waiting for the SSH container service: %w", err)

		default:
			conn, err := net.DialTimeout("tcp", fmt.Sprintf("%s:%d", ip, 22), 500*time.Millisecond)
			if err == nil {
				conn.Close()
				break waitForSSH
			}
		}
	}

	cli, err := ssh.Dial("tcp", fmt.Sprintf("%s:%d", ip, 22), &ssh.ClientConfig{
		User:            sshUser,
		Auth:            []ssh.AuthMethod{ssh.Password(checkID)},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
	})
	if err != nil {
		return nil, dID, fmt.Errorf("connect to the container using SSH: %w", err)
	}

	return cli, dID, nil
}

func (c *Check) stopDocker(ctx context.Context, id string) {
	out, err := exec.Command("docker", "rm", "-f", id).CombinedOutput()
	if err != nil {
		c.log.Error().Err(err).Str("docker_id", id).Bytes("output", out).Msg("destroy docker")
	}
}

func (c *Check) checkHypervisor(ctx context.Context, cli sdk.Interface, hyperID, templateID string, failSelfSigned bool) (DependenciesVersions, error) {
	host := cli.URL().Host
	checkID := fmt.Sprintf("check-%s", shortid.MustGenerate())

	log := c.log.With().Str("host", host).Str("hyper_id", hyperID).Str("id", checkID).Logger()

	log.Debug().Msg("creating check docker")

	ssh, dockerID, err := c.prepareDocker(ctx, checkID)
	if err != nil {
		if dockerID != "" {
			c.stopDocker(ctx, dockerID)
		}

		return DependenciesVersions{}, fmt.Errorf("prepare docker: %w", err)
	}

	defer c.stopDocker(ctx, dockerID)
	defer ssh.Close()

	deps, err := c.getDependenciesVersions(ssh)
	if err != nil {
		return deps, err
	}

	// Create desktop
	log.Debug().Msg("creating check desktop")
	d, err := cli.DesktopCreate(ctx, checkID, templateID)
	if err != nil {
		return deps, fmt.Errorf("create the desktop: %w", err)
	}

	dktp := sdk.GetString(d.ID)

	// This function is to ensure that no desktop is left in the system
	defer func() {
		if err := cli.DesktopStop(ctx, dktp); err != nil {
			// If there's a not found error, the desktop has already been deleted :)
			if errors.Is(err, sdk.ErrNotFound) {
				return
			}
		}
		ensureDesktopState(ctx, cli, dktp, "Stopped")
		cli.DesktopDelete(ctx, dktp)
	}()

	if _, err = ensureDesktopState(ctx, cli, dktp, "Stopped"); err != nil {
		return deps, err
	}

	// Force the hypervisor
	if err := cli.DesktopUpdate(ctx, dktp, sdk.DesktopUpdateOptions{
		ForcedHyp: []string{hyperID},
	}); err != nil {
		return deps, fmt.Errorf("force the hypervisor: %w", err)
	}

	// Start the desktop & wait for it
	log.Debug().Msg("starting check desktop")
	if err := cli.DesktopStart(ctx, dktp); err != nil {
		return deps, fmt.Errorf("start the desktop: %w", err)
	}

	d, err = ensureDesktopState(ctx, cli, dktp, "Started")
	if err != nil {
		return deps, err
	}

	// Test the VPN
	log.Debug().Msg("testing VPN")
	if err := c.testVPN(ctx, cli, ssh, sdk.GetString(d.IP)); err != nil {
		return deps, fmt.Errorf("test the VPN: %w", err)
	}

	// Test the viewers
	log.Debug().Msg("testing viewers")
	if err := c.testViewers(ctx, &log, cli, ssh, failSelfSigned, dktp); err != nil {
		return deps, err
	}

	// Stop the desktop & wait for it
	log.Debug().Msg("stopping check desktop")
	if err := cli.DesktopStop(ctx, dktp); err != nil {
		return deps, fmt.Errorf("stop the desktop: %w", err)
	}

	if _, err = ensureDesktopState(ctx, cli, dktp, "Stopped"); err != nil {
		return deps, err
	}

	// Stop the VPN
	if err := c.stopVPN(ctx, ssh); err != nil {
		return deps, fmt.Errorf("stop the VPN: %w", err)
	}

	// Remove the desktop
	log.Debug().Msg("deleting check desktop")
	if err := cli.DesktopDelete(ctx, dktp); err != nil {
		return deps, fmt.Errorf("delete the desktop: %w", err)
	}

	return deps, nil
}

func ensureDesktopState(ctx context.Context, cli sdk.Interface, id, state string) (*sdk.Desktop, error) {
	var d *sdk.Desktop
	var err error

	for i := 0; i < desktopTimeout; i++ {
		d, err = cli.DesktopGet(ctx, id)
		if err != nil {
			return d, fmt.Errorf("ensure desktop state: %v", err)
		}

		if sdk.GetString(d.State) == state {
			return d, nil
		}

		time.Sleep(time.Second)
	}

	return d, fmt.Errorf("timeout waiting for desktop state to be '%s'. Current state is '%s'", state, sdk.GetString(d.State))
}

func (c *Check) getDependenciesVersions(cli *ssh.Client) (DependenciesVersions, error) {
	b, err := sshExec.CombinedOutput(cli, "remmina --version")
	if err != nil {
		return DependenciesVersions{}, fmt.Errorf("get remmina version: %w: %s", err, b)
	}

	lines := strings.Split(strings.TrimSpace(string(b)), "\n")
	rmm := strings.Split(lines[len(lines)-1], " ")[2]

	b, err = sshExec.CombinedOutput(cli, "remote-viewer --version")
	if err != nil {
		return DependenciesVersions{}, fmt.Errorf("get remote viewer version: %w: %s", err, b)
	}
	rv := strings.Split(strings.TrimSpace(string(b)), " ")[2]

	b, err = sshExec.CombinedOutput(cli, "wg --version")
	if err != nil {
		return DependenciesVersions{}, fmt.Errorf("get wireguard version: %w: %s", err, b)
	}
	wg := strings.Split(strings.TrimSpace(string(b)), " ")[1]

	return DependenciesVersions{
		Remmina:      rmm,
		RemoteViewer: rv,
		WireGuard:    wg,
	}, nil
}
