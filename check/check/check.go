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
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
	sshExec "gitlab.com/isard/isardvdi/pkg/ssh"
	"golang.org/x/crypto/ssh"
)

const (
	desktopTimeout = 90
	sshUser        = "executor"
)

var ErrMaintenanceMode = errors.New("maintenance mode is activated")

type Interface interface {
	// Check ensures that the service itself is correctly running
	Check(ctx context.Context) error
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

func (c *Check) Check(ctx context.Context) error {
	return nil
}

func (c *Check) CheckIsardVDI(ctx context.Context, authMethod AuthMethod, auth Auth, host, templateID string, failSelfSigned, failMaintenance bool) (CheckResult, error) {
	token, err := c.auth(ctx, host, !failSelfSigned, authMethod, auth)
	if err != nil {
		return CheckResult{}, err
	}
	c.log.Debug().Msg("authenticated with api key")

	var clientOpts []ogenclient.Option
	if !failSelfSigned {
		clientOpts = append(clientOpts, ogenclient.WithIgnoreCerts())
	}
	httpClient := ogenclient.NewHTTPClient(clientOpts...)
	cli, err := apiv4.NewClient(host, ogenclient.APIv4Static{Token: token}, apiv4.WithClient(httpClient))
	if err != nil {
		return CheckResult{}, fmt.Errorf("create API client: %w", err)
	}

	v, err := cli.APIVersion(ctx)
	if err != nil {
		return CheckResult{}, fmt.Errorf("get IsardVDI version: %w", err)
	}
	version := v.IsardvdiVersion

	maintRes, err := cli.MaintenanceStatus(ctx)
	if err != nil {
		return CheckResult{IsardVDIVersion: version}, fmt.Errorf("get maintenance mode: %w", err)
	}
	maintOK, ok := maintRes.(*apiv4.MaintenanceStatusResponse)
	if !ok {
		return CheckResult{IsardVDIVersion: version}, fmt.Errorf("get maintenance mode: %w", ogenclient.AsAPIError(maintRes))
	}
	maintenance := maintOK.Enabled.Or(false)

	if failMaintenance && maintenance {
		return CheckResult{
			IsardVDIVersion: version,
			MaintenanceMode: maintenance,
		}, ErrMaintenanceMode
	}

	hypRes, err := cli.AdminHypervisorsList(ctx, apiv4.AdminHypervisorsListParams{})
	if err != nil {
		return CheckResult{IsardVDIVersion: version, MaintenanceMode: maintenance}, fmt.Errorf("list hypervisors: %w", err)
	}
	hypOK, ok := hypRes.(*apiv4.AdminHypervisorsListOKApplicationJSON)
	if !ok {
		return CheckResult{IsardVDIVersion: version, MaintenanceMode: maintenance}, fmt.Errorf("list hypervisors: %w", ogenclient.AsAPIError(hypRes))
	}
	h := []apiv4.AdminHypervisor(*hypOK)

	var wg sync.WaitGroup
	errCh := make(chan error, len(h))
	depsCh := make(chan DependenciesVersions, len(h))

	for _, hyper := range h {
		wg.Add(1)

		go func(hyper apiv4.AdminHypervisor) {
			defer wg.Done()

			c.log.Debug().Str("host", host).Str("id", hyper.ID).Msg("checking hypervisor")

			deps, err := c.checkHypervisor(ctx, cli, host, hyper.ID, templateID, failSelfSigned)
			if err != nil {
				c.log.Error().Str("host", host).Str("hypervisor", hyper.ID).Str("template_id", templateID).Err(err).Msg("check hypervisor")
				err = fmt.Errorf("check hypervisor '%s': %w", hyper.ID, err)
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
	token, err := c.auth(ctx, host, !failSelfSigned, authMethod, auth)
	if err != nil {
		return CheckResult{}, err
	}

	var clientOpts []ogenclient.Option
	if !failSelfSigned {
		clientOpts = append(clientOpts, ogenclient.WithIgnoreCerts())
	}
	httpClient := ogenclient.NewHTTPClient(clientOpts...)
	cli, err := apiv4.NewClient(host, ogenclient.APIv4Static{Token: token}, apiv4.WithClient(httpClient))
	if err != nil {
		return CheckResult{}, fmt.Errorf("create API client: %w", err)
	}

	v, err := cli.APIVersion(ctx)
	if err != nil {
		return CheckResult{}, fmt.Errorf("get IsardVDI version: %w", err)
	}
	version := v.IsardvdiVersion

	maintRes, err := cli.MaintenanceStatus(ctx)
	if err != nil {
		return CheckResult{}, fmt.Errorf("get maintenance mode: %w", err)
	}
	maintOK, ok := maintRes.(*apiv4.MaintenanceStatusResponse)
	if !ok {
		return CheckResult{}, fmt.Errorf("get maintenance mode: %w", ogenclient.AsAPIError(maintRes))
	}
	maintenance := maintOK.Enabled.Or(false)

	if failMaintenance && maintenance {
		return CheckResult{}, ErrMaintenanceMode
	}

	deps, err := c.checkHypervisor(ctx, cli, host, hyperID, templateID, failSelfSigned)
	if err != nil {
		c.log.Error().Str("host", host).Str("hypervisor", hyperID).Str("template_id", templateID).Err(err).Msg("check hypervisor")

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

func (c *Check) checkHypervisor(ctx context.Context, cli apiv4.Invoker, host, hyperID, templateID string, failSelfSigned bool) (DependenciesVersions, error) {
	checkID := fmt.Sprintf("check-%s", shortid.MustGenerate())

	log := c.log.With().Str("host", host).Str("hyper_id", hyperID).Str("id", checkID).Logger()

	log.Debug().Msg("creating check docker")

	sshCli, dockerID, err := c.prepareDocker(ctx, checkID)
	if err != nil {
		if dockerID != "" {
			c.stopDocker(ctx, dockerID)
		}

		return DependenciesVersions{}, fmt.Errorf("prepare docker: %w", err)
	}

	defer c.stopDocker(ctx, dockerID)
	defer sshCli.Close()

	deps, err := c.getDependenciesVersions(sshCli)
	if err != nil {
		return deps, err
	}

	// Create desktop
	log.Debug().Msg("creating check desktop")
	d, err := createDesktop(ctx, cli, checkID, templateID)
	if err != nil {
		return deps, fmt.Errorf("create the desktop: %w", err)
	}

	dktp := d.ID

	// This function is to ensure that no desktop is left in the system
	defer func() {
		if err := stopDesktop(ctx, cli, dktp); err != nil {
			if errors.Is(err, ogenclient.ErrNotFound) {
				return
			}
		}
		ensureDesktopState(ctx, cli, dktp, "Stopped")
		deleteDesktop(ctx, cli, dktp)
	}()

	if _, err = ensureDesktopState(ctx, cli, dktp, "Stopped"); err != nil {
		return deps, err
	}

	// Force the hypervisor
	if err := editDesktop(ctx, cli, dktp, &apiv4.DesktopEditRequest{
		ForcedHyp: []string{hyperID},
	}); err != nil {
		return deps, fmt.Errorf("force the hypervisor: %w", err)
	}

	// Start the desktop & wait for it
	log.Debug().Msg("starting check desktop")
	if err := startDesktop(ctx, cli, dktp); err != nil {
		return deps, fmt.Errorf("start the desktop: %w", err)
	}

	desktop, err := ensureDesktopState(ctx, cli, dktp, "Started")
	if err != nil {
		return deps, err
	}

	// Test the VPN
	log.Debug().Msg("testing VPN")
	if err := c.testVPN(ctx, cli, sshCli, desktop.IP.Or("")); err != nil {
		return deps, fmt.Errorf("test the VPN: %w", err)
	}

	// Test the viewers
	log.Debug().Msg("testing viewers")
	if err := c.testViewers(ctx, &log, cli, sshCli, failSelfSigned, dktp); err != nil {
		return deps, err
	}

	// Stop the desktop & wait for it
	log.Debug().Msg("stopping check desktop")
	if err := stopDesktop(ctx, cli, dktp); err != nil {
		return deps, fmt.Errorf("stop the desktop: %w", err)
	}

	if _, err = ensureDesktopState(ctx, cli, dktp, "Stopped"); err != nil {
		return deps, err
	}

	// Stop the VPN
	if err := c.stopVPN(ctx, sshCli); err != nil {
		return deps, fmt.Errorf("stop the VPN: %w", err)
	}

	// Remove the desktop
	log.Debug().Msg("deleting check desktop")
	if err := deleteDesktop(ctx, cli, dktp); err != nil {
		return deps, fmt.Errorf("delete the desktop: %w", err)
	}

	return deps, nil
}

func createDesktop(ctx context.Context, cli apiv4.Invoker, name, templateID string) (*apiv4.SimpleResponse, error) {
	res, err := cli.CreateDesktop(ctx, &apiv4.CreateDesktopRequest{
		TemplateID: templateID,
		Name:       name,
	})
	if err != nil {
		return nil, err
	}

	if v, ok := res.(*apiv4.SimpleResponse); ok {
		return v, nil
	}
	return nil, ogenclient.AsAPIError(res)
}

func stopDesktop(ctx context.Context, cli apiv4.Invoker, id string) error {
	res, err := cli.StopDesktop(ctx, apiv4.StopDesktopParams{DesktopID: id})
	if err != nil {
		return err
	}

	if _, ok := res.(*apiv4.SimpleResponse); ok {
		return nil
	}
	return ogenclient.AsAPIError(res)
}

func startDesktop(ctx context.Context, cli apiv4.Invoker, id string) error {
	res, err := cli.StartDesktop(ctx, apiv4.StartDesktopParams{DesktopID: id})
	if err != nil {
		return err
	}

	if _, ok := res.(*apiv4.SimpleResponse); ok {
		return nil
	}
	return ogenclient.AsAPIError(res)
}

func deleteDesktop(ctx context.Context, cli apiv4.Invoker, id string) error {
	res, err := cli.DeleteDesktop(ctx, apiv4.DeleteDesktopParams{DesktopID: id})
	if err != nil {
		return err
	}

	switch res.(type) {
	case *apiv4.DeleteDesktopNoContent, *apiv4.DeleteDesktopOK, *apiv4.DeleteDesktopAccepted:
		return nil
	}
	return ogenclient.AsAPIError(res)
}

func editDesktop(ctx context.Context, cli apiv4.Invoker, id string, req *apiv4.DesktopEditRequest) error {
	res, err := cli.EditDesktop(ctx, req, apiv4.EditDesktopParams{DesktopID: id})
	if err != nil {
		return err
	}

	if _, ok := res.(*apiv4.SimpleResponse); ok {
		return nil
	}
	return ogenclient.AsAPIError(res)
}

func ensureDesktopState(ctx context.Context, cli apiv4.Invoker, id, state string) (*apiv4.Desktop, error) {
	var d *apiv4.Desktop
	var err error

	for i := 0; i < desktopTimeout; i++ {
		d, err = getDesktop(ctx, cli, id)
		if err != nil {
			return d, fmt.Errorf("ensure desktop state: %w", err)
		}

		if string(d.Status) == state {
			return d, nil
		}

		time.Sleep(time.Second)
	}

	currentState := ""
	if d != nil {
		currentState = string(d.Status)
	}

	return d, fmt.Errorf("timeout waiting for desktop state to be '%s'. Current state is '%s'", state, currentState)
}

func getDesktop(ctx context.Context, cli apiv4.Invoker, id string) (*apiv4.Desktop, error) {
	res, err := cli.GetDesktop(ctx, apiv4.GetDesktopParams{DesktopID: id})
	if err != nil {
		return nil, err
	}

	if v, ok := res.(*apiv4.Desktop); ok {
		return v, nil
	}
	return nil, ogenclient.AsAPIError(res)
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
