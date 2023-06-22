package check

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net"
	"path/filepath"
	"strings"
	"time"

	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-cli/pkg/client"
	"gitlab.com/isard/isardvdi/pkg/ssh"
	stdSSH "golang.org/x/crypto/ssh"
)

// TODO: RDP Web, noVNC
func (c *Check) testViewers(ctx context.Context, log *zerolog.Logger, cli client.Interface, sshCli *stdSSH.Client, failSelfSigned bool, id string) error {
	// const port = 9000
	// service, err := selenium.NewGeckoDriverService("geckodriver", port)
	// if err != nil {
	// 	return fmt.Errorf("start the selenium service: %w", err)
	// }
	// defer service.Stop()

	// wd, err := selenium.NewRemote(selenium.Capabilities{"browserName": "firefox", firefox.CapabilitiesKey: firefox.Capabilities{Args: []string{"-headless"}}}, fmt.Sprintf("http://localhost:%d", port))
	// if err != nil {
	// 	return fmt.Errorf("connect to the selenium remote: %w", err)
	// }
	// defer wd.Quit()

	log.Debug().Str("viewer", string(client.DesktopViewerSpice)).Msg("testing viewer")
	if err := c.testSpice(ctx, cli, sshCli, id); err != nil {
		return err
	}

	log.Debug().Str("viewer", string(client.DesktopViewerRdpGW)).Msg("testing viewer")
	if err := c.testRdpGW(ctx, cli, sshCli, failSelfSigned, id); err != nil {
		return err
	}

	log.Debug().Str("viewer", string(client.DesktopViewerRdpVPN)).Msg("testing viewer")
	if err := c.testRdpVPN(ctx, cli, sshCli, failSelfSigned, id); err != nil {
		return err
	}

	// c.log.Debug().Str("viewer", string(client.DesktopViewerVNCBrowser)).Msg("testing viewer")
	// if err := testWebVNC(ctx, wd, cli, id); err != nil {
	// 	return err
	// }

	return nil
}

func (c *Check) testSpice(ctx context.Context, cli client.Interface, sshCli *stdSSH.Client, id string) error {
	spice, err := cli.DesktopViewer(ctx, client.DesktopViewerSpice, id)
	if err != nil {
		return fmt.Errorf("get spice viewer: %w", err)
	}

	path := "./console.vv"
	if err := ssh.WriteFile(sshCli, path, []byte(spice)); err != nil {
		return fmt.Errorf("write the spice viewer file: %w", err)
	}

	if err := testViewerCmd(sshCli, fmt.Sprintf("remote-viewer %s --spice-debug", path), "display-2:0: connect ready", nil); err != nil {
		return fmt.Errorf("viewer spice failed: %w", err)
	}

	return nil
}

func (c *Check) testRdpGW(ctx context.Context, cli client.Interface, sshCli *stdSSH.Client, failSelfSigned bool, id string) error {
	return c.testRDP(ctx, cli, sshCli, client.DesktopViewerRdpGW, failSelfSigned, id)
}

func (c *Check) testRdpVPN(ctx context.Context, cli client.Interface, sshCli *stdSSH.Client, failSelfSigned bool, id string) error {
	return c.testRDP(ctx, cli, sshCli, client.DesktopViewerRdpVPN, failSelfSigned, id)
}

func (c *Check) testRDP(ctx context.Context, cli client.Interface, sshCli *stdSSH.Client, viewer client.DesktopViewer, failSelfSigned bool, id string) error {
	rdp, err := cli.DesktopViewer(ctx, viewer, id)
	if err != nil {
		return fmt.Errorf("get %s viewer: %w", viewer, err)
	}

	path := fmt.Sprintf("./console-%s.rdp", viewer)
	if err := ssh.WriteFile(sshCli, path, []byte(rdp)); err != nil {
		return fmt.Errorf("save the %s viewer file: %w", viewer, err)
	}

	if b, err := ssh.CombinedOutput(sshCli, `echo "G_MESSAGES_PREFIXED=all" | sudo tee -a /env`); err != nil {
		return fmt.Errorf("setup environment variables for %s: %w: %s", viewer, err, string(b))
	}

	if b, err := ssh.CombinedOutput(sshCli, `echo "G_MESSAGES_DEBUG=all" | sudo tee -a /env`); err != nil {
		return fmt.Errorf("setup environment variables for %s: %w: %s", viewer, err, string(b))
	}

	if err := testViewerCmd(
		sshCli,
		fmt.Sprintf("remmina %s", path),
		"freerdp.channels.drdynvc.client] - Loading Dynamic Virtual Channel disp",
		func(b []byte) error {
			if strings.Contains(string(b), "@           WARNING: CERTIFICATE NAME MISMATCH!           @") {
				if failSelfSigned {
					return errors.New("self signed certificate found in RDP Gateway")
				}

				var host, port string
				for _, l := range strings.Split(rdp, "\n") {
					if strings.HasPrefix(l, "gatewayhostname:s:") {
						host, port, err = net.SplitHostPort(strings.TrimSpace(strings.TrimPrefix(l, "gatewayhostname:s:")))
						if err != nil {
							return fmt.Errorf("parse RDP GW host port: %w", err)
						}

						break
					}
				}

				if err := remminaAcceptCertificate(sshCli, host, port); err != nil {
					return fmt.Errorf("accept certificate: %w", err)
				}
			}

			return nil
		},
	); err != nil {
		return fmt.Errorf("viewer %s failed: %w", viewer, err)
	}

	return nil
}

func remminaAcceptCertificate(sshCli *stdSSH.Client, host, port string) error {
	conn, err := net.Dial("tcp", net.JoinHostPort(host, port))
	if err != nil {
		return fmt.Errorf("dial the host: %w", err)
	}
	defer conn.Close()

	tlsConn := tls.Client(conn, &tls.Config{
		InsecureSkipVerify: true,
	})
	if err := tlsConn.Handshake(); err != nil {
		return fmt.Errorf("read the TLS certificate: %w", err)
	}

	state := tlsConn.ConnectionState()

	sha := sha256.Sum256(state.PeerCertificates[0].Raw)

	hexF := hex.EncodeToString(sha[0:])
	fingerprint := []byte{}
	for i := 0; i < len(hexF); i += 2 {
		fingerprint = append(fingerprint, hexF[i], hexF[i+1], ':')
	}
	fingerprint = fingerprint[:len(fingerprint)-1]

	issuer := base64.StdEncoding.EncodeToString([]byte(state.PeerCertificates[0].Issuer.String()))
	subject := base64.StdEncoding.EncodeToString([]byte(state.PeerCertificates[0].Subject.String()))

	cfgDir := "$HOME/.config/freerdp"
	if err := ssh.MkdirAll(sshCli, cfgDir); err != nil {
		return fmt.Errorf("create the frrerdp config directory: %w", err)
	}

	if err := ssh.WriteFile(sshCli, filepath.Join(cfgDir, "known_hosts2"), []byte(fmt.Sprintf("%s %s %s %s %s", host, port, fingerprint, issuer, subject))); err != nil {
		return fmt.Errorf("write certificate to file: %w", err)
	}

	return nil
}

func testViewerCmd(sshCli *stdSSH.Client, command string, expected string, hook func([]byte) error) error {
	out := []byte{}
attemptsLoop:
	for attempts := 0; attempts < 3; attempts++ {
		buf := &bytes.Buffer{}

		sess, err := sshCli.NewSession()
		if err != nil {
			return fmt.Errorf("create SSH session: %w", err)
		}
		defer sess.Close()

		sess.Stdout = buf
		sess.Stderr = buf

		if err := sess.Start(fmt.Sprintf("set -a && source /env && set +a && export $(dbus-launch) && %s", command)); err != nil {
			continue
		}

		finished := make(chan error, 1)
		go func() {
			finished <- sess.Wait()
		}()

		timeout := time.After(60 * time.Second)
	waitCommandFinish:
		for {
			select {
			case <-finished:
				break waitCommandFinish

			case <-timeout:
				sess.Signal(stdSSH.SIGKILL)
				break waitCommandFinish

			default:
				b, err := io.ReadAll(buf)
				out = append(out, b...)
				if err != nil {
					sess.Signal(stdSSH.SIGKILL)
					continue attemptsLoop
				}

				if hook != nil {
					if err := hook(b); err != nil {
						sess.Signal(stdSSH.SIGKILL)
						return err
					}
				}

				if strings.Contains(string(b), expected) {
					sess.Signal(stdSSH.SIGKILL)
					return nil
				}

				time.Sleep(time.Second)
			}

		}
	}

	return fmt.Errorf("run out of attempts: \n%s", out)
}

// func testWebVNC(ctx context.Context, wd selenium.WebDriver, cli client.Interface, id string) error {
// 	vnc, err := cli.DesktopViewer(ctx, client.DesktopViewerVNCBrowser, id)
// 	if err != nil {
// 		return fmt.Errorf("get web vnc viewer: %w", err)
// 	}

// 	if err := wd.Get(vnc); err != nil {
// 		return fmt.Errorf("navigate to the viewer page: %w", err)
// 	}

// 	return errors.New("not implemented yet, GECKO!!")
// }
