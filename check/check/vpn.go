package check

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"gitlab.com/isard/isardvdi-sdk-go"
	"gitlab.com/isard/isardvdi/pkg/ssh"
	stdSSH "golang.org/x/crypto/ssh"
)

func (c *Check) testVPN(ctx context.Context, cli isardvdi.Interface, sshCli *stdSSH.Client, ip string) error {
	vpn, err := cli.UserVPN(ctx)
	if err != nil {
		return fmt.Errorf("get the VPN file: %w", err)
	}

	fPath := fmt.Sprintf("./%d.conf", time.Now().Unix())
	if err := ssh.WriteFile(sshCli, fPath, []byte(vpn)); err != nil {
		return fmt.Errorf("save VPN configuration: %w", err)
	}

	b, err := ssh.CombinedOutput(sshCli, fmt.Sprintf("wg-quick up %s", fPath))
	if err != nil {
		return fmt.Errorf("activate VPN connection: %w: %s", err, b)
	}

	b, err = ssh.CombinedOutput(sshCli, fmt.Sprintf("ping -c 6 %s", ip))
	if err != nil {
		c.stopVPN(ctx, sshCli)
		return fmt.Errorf("ping the desktop: %w: %s", err, b)
	}

	pktLoss, err := strconv.ParseFloat(strings.TrimSpace(strings.Split(strings.Split(string(b), ",")[2], "%")[0]), 32)
	if err != nil {
		c.stopVPN(ctx, sshCli)
		return fmt.Errorf("get the packet loss: %w", err)
	}

	if pktLoss > 50 {
		c.stopVPN(ctx, sshCli)
		return errors.New("VPN test failed")
	}

	return nil
}

func (c *Check) stopVPN(ctx context.Context, sshCli *stdSSH.Client) error {
	b, err := ssh.CombinedOutput(sshCli, `sudo wg | grep interface | awk -F ": " '{ print $2 }'`)
	if err != nil {
		return fmt.Errorf("find wireguard interface: %w: %s", err, b)
	}

	i := strings.TrimSpace(string(b))

	if b, err := ssh.CombinedOutput(sshCli, fmt.Sprintf("wg-quick down ./%s.conf", i)); err != nil {
		return fmt.Errorf("stop the VPN connection: %w: %s", err, b)
	}

	return nil
}
