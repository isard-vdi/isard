package check

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os/exec"
	"strings"
	"time"

	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-cli/pkg/cfg"
	"gitlab.com/isard/isardvdi-cli/pkg/client"
	"golang.org/x/crypto/ssh"
)

const desktopTimeout = 60

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
}

func NewCheck(log *zerolog.Logger) *Check {
	return &Check{log}
}

func (c *Check) CheckIsardVDI(ctx context.Context, authMethod AuthMethod, auth Auth, host, templateID string, failSelfSigned, failMaintenance bool) (CheckResult, error) {
	cli, err := client.NewClient(&cfg.Cfg{
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
		return CheckResult{}, errors.New("maintenance mode is activated")
	}

	h, err := cli.HypervisorList(ctx)
	if err != nil {
		return CheckResult{}, fmt.Errorf("list hypervisors: %w", err)
	}

	for _, hyper := range h {
		c.log.Debug().Str("id", *hyper.ID).Msg("checking hypervisor")

		if err := c.checkHypervisor(ctx, cli, client.GetString(hyper.ID), templateID, failSelfSigned); err != nil {
			c.log.Error().Str("hypervisor", client.GetString(hyper.ID)).Str("template_id", templateID).Err(err).Msg("check hypervisor")

			return CheckResult{}, fmt.Errorf("check hypervisor: %w", err)
		}
	}

	deps, err := c.getDependenciesVersions()
	if err != nil {
		return CheckResult{}, fmt.Errorf("get dependencies versions: %w", err)
	}

	return CheckResult{
		IsardVDIVersion:      version,
		MaintenanceMode:      maintenance,
		DependenciesVersions: deps,
		HypervisorNum:        len(h),
	}, nil
}

func (c *Check) CheckHypervisor(ctx context.Context, authMethod AuthMethod, auth Auth, host, hyperID, templateID string, failSelfSigned, failMaintenance bool) (CheckResult, error) {
	cli, err := client.NewClient(&cfg.Cfg{
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
		return CheckResult{}, errors.New("maintenance mode is activated")
	}

	if err := c.checkHypervisor(ctx, cli, hyperID, templateID, failSelfSigned); err != nil {
		c.log.Error().Str("hypervisor", hyperID).Str("template_id", templateID).Err(err).Msg("check hypervisor")

		return CheckResult{}, fmt.Errorf("check hypervisor: %w", err)
	}

	deps, err := c.getDependenciesVersions()
	if err != nil {
		return CheckResult{}, fmt.Errorf("get dependencies versions: %w", err)
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

	out, err = exec.Command("bash", "-c", fmt.Sprintf(`docker run -d --name "%s" --network "%s" --cap-add=NET_ADMIN "$(docker inspect isard-check | jq -j '.[0].Image' | awk -F ":" '{ print $2 }')" bash -c 'echo "root:%s" | chpasswd && dropbear -RFE'`, checkID, netName, checkID)).CombinedOutput()
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
		User:            "root",
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

func (c *Check) checkHypervisor(ctx context.Context, cli client.Interface, hyperID, templateID string, failSelfSigned bool) error {
	checkID := fmt.Sprintf("check-%d", time.Now().Unix())

	c.log.Debug().Str("hyper_id", hyperID).Str("id", checkID).Msg("creating check docker")

	ssh, dockerID, err := c.prepareDocker(ctx, checkID)
	if err != nil {
		if dockerID != "" {
			c.stopDocker(ctx, dockerID)
		}

		return fmt.Errorf("prepare docker: %w", err)
	}

	defer c.stopDocker(ctx, dockerID)
	defer ssh.Close()

	// Create desktop
	c.log.Debug().Str("hyper_id", hyperID).Str("id", checkID).Msg("creating check desktop")
	d, err := cli.DesktopCreate(ctx, checkID, templateID)
	if err != nil {
		return fmt.Errorf("create the desktop: %w", err)
	}

	dktp := client.GetString(d.ID)

	// This function is to ensure that no desktop is left in the system
	defer func() {
		if err := cli.DesktopStop(ctx, dktp); err != nil {
			// If there's a not found error, the desktop has already been deleted :)
			if errors.Is(err, client.ErrNotFound) {
				return
			}
		}
		ensureDesktopState(ctx, cli, dktp, "Stopped")
		cli.DesktopDelete(ctx, dktp)
	}()

	if _, err = ensureDesktopState(ctx, cli, dktp, "Stopped"); err != nil {
		return err
	}

	// Force the hypervisor
	if err := cli.DesktopUpdate(ctx, dktp, client.DesktopUpdateOptions{
		ForcedHyp: []string{hyperID},
	}); err != nil {
		return fmt.Errorf("force the hypervisor: %w", err)
	}

	// Start the desktop & wait for it
	c.log.Debug().Str("hyper_id", hyperID).Str("id", checkID).Msg("starting check desktop")
	if err := cli.DesktopStart(ctx, dktp); err != nil {
		return fmt.Errorf("start the desktop: %w", err)
	}

	d, err = ensureDesktopState(ctx, cli, dktp, "Started")
	if err != nil {
		return err
	}

	// Test the VPN
	c.log.Debug().Str("hyper_id", hyperID).Str("id", checkID).Msg("testing VPN")
	if err := c.testVPN(ctx, cli, ssh, client.GetString(d.IP)); err != nil {
		return fmt.Errorf("test the VPN: %w", err)
	}

	// Test the viewers
	c.log.Debug().Str("hyper_id", hyperID).Str("id", checkID).Msg("testing viewers")
	if err := c.testViewers(ctx, cli, ssh, failSelfSigned, dktp); err != nil {
		return err
	}

	// Stop the desktop & wait for it
	c.log.Debug().Str("hyper_id", hyperID).Str("id", checkID).Msg("stopping check desktop")
	if err := cli.DesktopStop(ctx, dktp); err != nil {
		return fmt.Errorf("stop the desktop: %w", err)
	}

	if _, err = ensureDesktopState(ctx, cli, dktp, "Stopped"); err != nil {
		return err
	}

	// Stop the VPN
	if err := c.stopVPN(ctx, ssh); err != nil {
		return fmt.Errorf("stop the VPN: %w", err)
	}

	// Remove the desktop
	c.log.Debug().Str("hyper_id", hyperID).Str("id", checkID).Msg("deleting check desktop")
	if err := cli.DesktopDelete(ctx, dktp); err != nil {
		return fmt.Errorf("delete the desktop: %w", err)
	}

	return nil
}

func ensureDesktopState(ctx context.Context, cli client.Interface, id, state string) (*client.Desktop, error) {
	var d *client.Desktop
	var err error

	for i := 0; i < desktopTimeout; i++ {
		d, err = cli.DesktopGet(ctx, id)
		if err != nil {
			return d, fmt.Errorf("ensure desktop state: %v", err)
		}

		if client.GetString(d.State) == state {
			return d, nil
		}

		time.Sleep(time.Second)
	}

	return d, fmt.Errorf("timeout waiting for desktop state to be '%s'. Current state is '%s'", state, client.GetString(d.State))
}

func (c *Check) getDependenciesVersions() (DependenciesVersions, error) {
	b, err := exec.Command("remmina", "--version").CombinedOutput()
	if err != nil {
		return DependenciesVersions{}, fmt.Errorf("get remmina version: %w: %s", err, b)
	}

	lines := strings.Split(strings.TrimSpace(string(b)), "\n")
	rmm := strings.Split(lines[len(lines)-1], " ")[2]

	b, err = exec.Command("remote-viewer", "--version").CombinedOutput()
	if err != nil {
		return DependenciesVersions{}, fmt.Errorf("get remote viewer version: %w: %s", err, b)
	}
	rv := strings.Split(strings.TrimSpace(string(b)), " ")[2]

	b, err = exec.Command("wg", "--version").CombinedOutput()
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
