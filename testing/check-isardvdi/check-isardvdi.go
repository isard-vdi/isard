package main

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
	"log"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"gitlab.com/isard/isardvdi-cli/pkg/cfg"
	"gitlab.com/isard/isardvdi-cli/pkg/client"
)

const (
	desktopTimeout = 60
	viewerTimeout  = 60
)

var (
	host                = "https://localhost"
	usr                 = "admin"
	pwd                 = "IsardVDI"
	dskt                = "_local-default-admin-admin_downloaded_slax93"
	failSelfSigned      = false
	failMaintenanceMode = false
)

func main() {
	// get config
	getCfg()

	// ensure dependencies
	if err := checkDeps(); err != nil {
		log.Fatalln(err)
	}

	cli, err := client.NewClient(&cfg.Cfg{
		Host:        host,
		IgnoreCerts: true,
	})
	if err != nil {
		log.Fatalf("create isardvdi client: %v", err)
	}

	ctx := context.Background()
	version, err := cli.Version(ctx)
	if err != nil {
		log.Fatalf("get IsardVDI version: %v", err)
	}

	maintenance, err := cli.Maintenance(ctx)
	if err != nil {
		log.Fatalf("get IsardVDI maintenance mode: %v", err)
	}

	if maintenance && failMaintenanceMode {
		log.Fatal("maintenance mode is enabled")
	}

	// print info
	fmt.Println(`
██╗███████╗ █████╗ ██████╗ ██████╗ ██╗   ██╗██████╗ ██╗    ████████╗███████╗███████╗████████╗███████╗██████╗ 
██║██╔════╝██╔══██╗██╔══██╗██╔══██╗██║   ██║██╔══██╗██║    ╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝██╔════╝██╔══██╗
██║███████╗███████║██████╔╝██║  ██║██║   ██║██║  ██║██║       ██║   █████╗  ███████╗   ██║   █████╗  ██████╔╝
██║╚════██║██╔══██║██╔══██╗██║  ██║╚██╗ ██╔╝██║  ██║██║       ██║   ██╔══╝  ╚════██║   ██║   ██╔══╝  ██╔══██╗
██║███████║██║  ██║██║  ██║██████╔╝ ╚████╔╝ ██████╔╝██║       ██║   ███████╗███████║   ██║   ███████╗██║  ██║
╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝   ╚═══╝  ╚═════╝ ╚═╝       ╚═╝   ╚══════╝╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝`)
	info, err := exec.Command("cowsay", "-W", "80", "-f", "/isard.cow", fmt.Sprintf(`
IsardVDI Client: %s

Remmina: %s

Remote Viewer: %s

Wireguard: %s

-------

Host: %s

IsardVDI Version: %s

IsardVDI Maintenance mode: %t

Date: %s`, client.Version, deps["remmina"], deps["remote-viewer"], deps["wg-quick"], host, version, maintenance, time.Now().Format(time.RFC3339))).CombinedOutput()
	if err != nil {
		log.Fatalf("print system info: %v", err)
	}
	fmt.Println(string(info))

	// login
	fmt.Println("Running tests...")
	fmt.Println("[1/4] Attempting to login...")
	tkn, err := cli.AuthForm(ctx, "default", usr, pwd)
	if err != nil {
		log.Fatalf("login error: %v", err)
	}

	cli.Token = tkn

	// check if desktop is downloaded
	fmt.Println("[2/4] Check if the desktop is downloaded...")
	d, err := cli.DesktopGet(ctx, dskt)
	if err != nil {
		// TODO: If it's not found, download it!
		log.Fatalf("get desktop: %v", err)
	}

	// check if desktop is stopped
	fmt.Println("[3/4] Ensuring the desktop is stopped...")
	if client.GetString(d.State) != "Stopped" {
		if err := cli.DesktopStop(ctx, dskt); err != nil {
			log.Fatalf("stop desktop: %v", err)
		}

		if _, err := ensureDesktopState(ctx, cli, dskt, "Stopped"); err != nil {
			log.Fatalln(err)
		}
	}

	// get all the hypervisors
	fmt.Println("[4/4] Listing hypervisors...")
	hypers, err := cli.HypervisorList(ctx)
	if err != nil {
		log.Fatalf("list hypervisors: %v", err)
	}

	wd, err := os.Getwd()
	if err != nil {
		log.Fatalf("get current directory: %v", err)
	}

	for _, h := range hypers {
		fmt.Printf("\nRunning tests in hypervisor '%s'...\n", client.GetString(h.ID))
		tmp, err := os.MkdirTemp("", "check-isardvdi")
		if err != nil {
			log.Panicf("create temp directory: %v", err)
		}

		if err := os.Chdir(tmp); err != nil {
			log.Panicf("change to the temp directory: %v", err)
		}

		defer func() {
			if err := os.Chdir(wd); err != nil {
				log.Panicf("change to the original directory: %v", err)
			}

			if err := os.RemoveAll(tmp); err != nil {
				log.Panicf("remove temp directory: %v", err)
			}
		}()

		// force the hypervisor
		fmt.Println("[1/9] Force the hypervisor...")
		if err := cli.DesktopUpdate(ctx, dskt, client.DesktopUpdateOptions{
			ForcedHyp: []string{client.GetString(h.ID)},
		}); err != nil {
			onError(tmp, fmt.Errorf("force hypervisor: %w", err))
		}

		// start the desktop
		fmt.Println("[2/9] Start the desktop...")
		if err := cli.DesktopStart(ctx, dskt); err != nil {
			onError(tmp, fmt.Errorf("start desktop: %w", err))
		}

		// check that is started
		fmt.Println("[3/9] Ensuring the desktop is started...")
		d, err := ensureDesktopState(ctx, cli, dskt, "Started")
		if err != nil {
			onError(tmp, err)
		}

		// test vpn
		fmt.Println("[4/9] Testing the VPN connection...")
		if err := testVPN(ctx, cli, client.GetString(d.IP)); err != nil {
			onError(tmp, err)
		}

		if err := testViewers(ctx, cli); err != nil {
			onError(tmp, err)
		}

		// stop the desktop
		fmt.Println("[8/9] Stop the desktop...")
		if err := cli.DesktopStop(ctx, dskt); err != nil {
			onError(tmp, fmt.Errorf("stop desktop: %w", err))
		}

		// check that the desktop is stopped
		fmt.Println("[9/9] Ensuring the desktop is stopped...")
		if _, err := ensureDesktopState(ctx, cli, dskt, "Stopped"); err != nil {
			onError(tmp, err)
		}

		stopVPN()
	}

	fmt.Println("\nAll tests passed successfully! IsardVDI works! :)")
}

func onError(tmp string, err error) {
	stopVPN()

	fmt.Println("--- error ---")
	fmt.Printf("temporary directory: %s\n", tmp)
	fmt.Println(err)
	os.Exit(1)
}

func getCfg() {
	if h := os.Getenv("HOST"); h != "" {
		host = h
	}

	if u := os.Getenv("USERNAME"); u != "" {
		usr = u
	}

	if p := os.Getenv("PASSWORD"); p != "" {
		pwd = p
	}

	if d := os.Getenv("DESKTOP_ID"); d != "" {
		dskt = d
	}

	if f := os.Getenv("FAIL_MAINTENANCE_MODE"); f == "true" {
		failMaintenanceMode = true
	}

	if f := os.Getenv("FAIL_SELF_SIGNED"); f == "true" {
		failSelfSigned = true
	}
}

var deps = map[string]string{
	"cowsay":        "",
	"wg-quick":      "",
	"ping":          "",
	"remote-viewer": "",
	"remmina":       "",
}

func checkDeps() error {
	for d := range deps {
		if _, err := exec.LookPath(d); err != nil {
			return fmt.Errorf("missing dependency: '%s'", d)
		}

		switch d {
		case "wg-quick":
			b, err := exec.Command("wg", "--version").CombinedOutput()
			if err != nil {
				return fmt.Errorf("get %s version: %w", d, err)
			}

			deps[d] = strings.Split(strings.TrimSpace(string(b)), " ")[1]

		case "remote-viewer":
			b, err := exec.Command("remote-viewer", "--version").CombinedOutput()
			if err != nil {
				return fmt.Errorf("get %s version: %w", d, err)
			}

			deps[d] = strings.Split(strings.TrimSpace(string(b)), " ")[2]

		case "remmina":
			b, err := exec.Command("remmina", "--version").CombinedOutput()
			if err != nil {
				return fmt.Errorf("get %s version: %w", d, err)
			}

			lines := strings.Split(strings.TrimSpace(string(b)), "\n")
			deps[d] = strings.Split(lines[len(lines)-1], " ")[2]

		}
	}

	return nil
}

func ensureDesktopState(ctx context.Context, cli *client.Client, id, state string) (*client.Desktop, error) {
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

func testVPN(ctx context.Context, cli *client.Client, ip string) error {
	vpn, err := cli.UserVPN(ctx)
	if err != nil {
		return fmt.Errorf("get the VPN file: %w", err)
	}

	if err := os.WriteFile("isard.conf", []byte(vpn), 0600); err != nil {
		return fmt.Errorf("save VPN configuration: %w", err)
	}

	b, err := exec.Command("wg-quick", "up", "./isard.conf").CombinedOutput()
	if err != nil {
		return fmt.Errorf("activate VPN connection: %w, %s", err, b)
	}

	b, err = exec.Command("ping", "-c", "6", ip).CombinedOutput()
	if err != nil {
		stopVPN()
		return fmt.Errorf("ping the desktop: %w, %s", err, b)
	}

	pktLoss, err := strconv.ParseFloat(strings.TrimSpace(strings.Split(strings.Split(string(b), ",")[2], "%")[0]), 32)
	if err != nil {
		stopVPN()
		return fmt.Errorf("get the packet loss: %w", err)
	}

	if pktLoss > 50 {
		stopVPN()
		return errors.New("VPN test failed")
	}

	return nil
}

func stopVPN() error {
	if b, err := exec.Command("wg-quick", "down", "./isard.conf").CombinedOutput(); err != nil {
		return fmt.Errorf("stop VPN: %w: %s", err, b)
	}

	return nil
}

func testViewers(ctx context.Context, cli *client.Client) error {
	fmt.Println("[5/9] Test the SPICE viewer...")
	if err := testSpice(ctx, cli); err != nil {
		return err
	}

	fmt.Println("[6/9] Test the RDP Gateway viewer...")
	if err := testRdpGW(ctx, cli); err != nil {
		return err
	}

	fmt.Println("[7/9] Test the RDP VPN viewer...")
	if err := testRdpVPN(ctx, cli); err != nil {
		return err
	}

	return nil
}

func testViewer(command []string, expected string, hook func([]byte) error) error {
	out := []byte{}
	for attempts := 0; attempts < 3; attempts++ {
		buf := &bytes.Buffer{}

		cmd := exec.Command(command[0], command[1:]...)
		cmd.Stdout = buf
		cmd.Stderr = buf

		if err := cmd.Start(); err != nil {
			continue
		}

		for i := 0; i < viewerTimeout; i++ {
			b, err := io.ReadAll(buf)
			out = append(out, b...)
			if err != nil {
				syscall.Kill(cmd.Process.Pid, syscall.SIGKILL)

				continue
			}

			if hook != nil {
				if err := hook(b); err != nil {
					syscall.Kill(cmd.Process.Pid, syscall.SIGKILL)

					return err
				}
			}

			if strings.Contains(string(b), expected) {
				syscall.Kill(cmd.Process.Pid, syscall.SIGKILL)

				return nil
			}

			time.Sleep(time.Second)
		}

		syscall.Kill(cmd.Process.Pid, syscall.SIGKILL)
	}

	return fmt.Errorf("run out of attempts: \n%s", out)
}

func testSpice(ctx context.Context, cli *client.Client) error {
	spice, err := cli.DesktopViewer(ctx, client.DesktopViewerSpice, dskt)
	if err != nil {
		return fmt.Errorf("get spice viewer: %w", err)
	}

	if err := os.WriteFile("console.vv", []byte(spice), 0644); err != nil {
		return fmt.Errorf("write the spice viewer file: %w", err)
	}

	if err := testViewer([]string{"remote-viewer", "console.vv", "--spice-debug"}, "display-2:0: connect ready", nil); err != nil {
		return fmt.Errorf("viewer spice failed: %w", err)
	}

	return nil
}

func remminaAcceptCertificate(host, port string) error {
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

	cfgDir := os.Getenv("XDG_CONFIG_HOME")
	if cfgDir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return fmt.Errorf("get home directory: %w", err)
		}

		cfgDir = filepath.Join(home, ".config")
	}

	cfgDir = filepath.Join(cfgDir, "freerdp")
	if _, err := os.Stat(cfgDir); err != nil {
		if !errors.Is(err, os.ErrNotExist) {
			return fmt.Errorf("check if the freerdp config directory exists: %w", err)
		}

		if err := os.MkdirAll(cfgDir, 0755); err != nil {
			return fmt.Errorf("create the freerdp config directory: %w", err)
		}

		fmt.Println("created dir! :D")
	}

	if err := os.WriteFile(filepath.Join(cfgDir, "known_hosts2"), []byte(fmt.Sprintf("%s %s %s %s %s", host, port, fingerprint, issuer, subject)), 0644); err != nil {
		return fmt.Errorf("write certificate to file: %w", err)
	}

	return nil
}

func testRDP(ctx context.Context, cli *client.Client, viewer client.DesktopViewer) error {
	rdp, err := cli.DesktopViewer(ctx, viewer, dskt)
	if err != nil {
		return fmt.Errorf("get %s viewer: %w", viewer, err)
	}

	if err := os.WriteFile(fmt.Sprintf("console-%s.rdp", viewer), []byte(rdp), 0644); err != nil {
		return fmt.Errorf("write the %s viewer file: %w", viewer, err)
	}

	if err := os.Setenv("G_MESSAGES_PREFIXED", "all"); err != nil {
		return fmt.Errorf("set remmina env variable: %w", err)
	}

	if err := os.Setenv("G_MESSAGES_DEBUG", "all"); err != nil {
		return fmt.Errorf("set remmina env variable: %w", err)
	}

	if err := testViewer(
		[]string{"remmina", fmt.Sprintf("./console-%s.rdp", viewer)},
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

				if err := remminaAcceptCertificate(host, port); err != nil {
					return fmt.Errorf("accept certificate: %w", err)
				}

				fmt.Println("\n---------- ACCEPTED SELF SIGNED CERTIFICATE ----------\n")
			}

			return nil
		},
	); err != nil {
		return fmt.Errorf("viewer %s failed: %w", viewer, err)
	}

	if err := os.Setenv("G_MESSAGES_PREFIXED", ""); err != nil {
		return fmt.Errorf("unset remmina env variable: %w", err)
	}
	if err := os.Setenv("G_MESSAGES_DEBUG", ""); err != nil {
		return fmt.Errorf("unset remmina env variable: %w", err)
	}

	return nil
}

func testRdpGW(ctx context.Context, cli *client.Client) error {
	return testRDP(ctx, cli, client.DesktopViewerRdpGW)
}

func testRdpVPN(ctx context.Context, cli *client.Client) error {
	return testRDP(ctx, cli, client.DesktopViewerRdpVPN)
}
