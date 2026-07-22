package ssh

import (
	"crypto/rand"
	"crypto/rsa"
	"io"
	"net"
	"strings"
	"testing"
	"time"

	"context"

	"github.com/rs/zerolog"
	"golang.org/x/crypto/ssh"
)

// These tests exercise handleChannel — the transparent SSH channel proxy — with
// an in-process client, bastion, and "guest" sshd, no rethinkdb / IsardVDI stack.
// They pin the regression where a non-interactive session (`ssh host 'cmd'`,
// piped stdin) was torn down the moment the client half-closed its stdin, so the
// command's output and exit-status never reached the client (exit 255). The guest
// deliberately writes its reply AFTER draining the client's stdin, so a premature
// teardown loses it.

func mustSigner(t *testing.T) ssh.Signer {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate host key: %v", err)
	}
	signer, err := ssh.NewSignerFromKey(key)
	if err != nil {
		t.Fatalf("signer: %v", err)
	}
	return signer
}

// startGuest starts a minimal backend sshd that, for an "exec" or "shell"
// request, reads the whole channel stdin, writes back "GOT:<stdin>", and sends an
// exit-status (7 if the exec command is "exit7", else 0). It models a real guest:
// the reply is produced only after stdin EOF.
func startGuest(t *testing.T) (addr string, stop func()) {
	t.Helper()
	cfg := &ssh.ServerConfig{
		PasswordCallback: func(ssh.ConnMetadata, []byte) (*ssh.Permissions, error) { return nil, nil },
	}
	cfg.AddHostKey(mustSigner(t))

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("guest listen: %v", err)
	}

	go func() {
		for {
			nConn, err := ln.Accept()
			if err != nil {
				return
			}
			go func() {
				sConn, chans, reqs, err := ssh.NewServerConn(nConn, cfg)
				if err != nil {
					return
				}
				defer sConn.Close()
				go ssh.DiscardRequests(reqs)
				for nc := range chans {
					if nc.ChannelType() != "session" {
						nc.Reject(ssh.UnknownChannelType, "only session")
						continue
					}
					ch, chReqs, err := nc.Accept()
					if err != nil {
						return
					}
					go serveGuestSession(ch, chReqs)
				}
			}()
		}
	}()

	return ln.Addr().String(), func() { ln.Close() }
}

func serveGuestSession(ch ssh.Channel, reqs <-chan *ssh.Request) {
	for req := range reqs {
		switch req.Type {
		case "exec", "shell":
			var payload struct{ Command string }
			if req.Type == "exec" {
				ssh.Unmarshal(req.Payload, &payload)
			}
			if req.WantReply {
				req.Reply(true, nil)
			}
			// Reply only AFTER draining stdin — mimics a real command reading
			// its input then producing output.
			data, _ := io.ReadAll(ch)
			io.WriteString(ch, "GOT:"+string(data))
			io.WriteString(ch.Stderr(), "ERR:"+payload.Command)
			var status uint32
			if payload.Command == "exit7" {
				status = 7
			}
			ch.SendRequest("exit-status", false, ssh.Marshal(struct{ Status uint32 }{status}))
			ch.Close()
			return
		default:
			if req.WantReply {
				req.Reply(false, nil)
			}
		}
	}
}

// startBastion dials the guest once and fronts an SSH server whose every session
// channel is proxied through handleChannel (the code under test).
func startBastion(t *testing.T, guestAddr string) (addr string, stop func()) {
	t.Helper()
	targetConn, err := ssh.Dial("tcp", guestAddr, &ssh.ClientConfig{
		User:            "guest",
		Auth:            []ssh.AuthMethod{ssh.Password("x")},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
		Timeout:         5 * time.Second,
	})
	if err != nil {
		t.Fatalf("dial guest: %v", err)
	}

	fcfg := &ssh.ServerConfig{NoClientAuth: true}
	fcfg.AddHostKey(mustSigner(t))

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("bastion listen: %v", err)
	}

	nop := zerolog.Nop()
	b := &bastion{log: &nop}
	ctx := context.Background()

	go func() {
		for {
			nConn, err := ln.Accept()
			if err != nil {
				return
			}
			go func() {
				sConn, chans, reqs, err := ssh.NewServerConn(nConn, fcfg)
				if err != nil {
					return
				}
				defer sConn.Close()
				go ssh.DiscardRequests(reqs)
				for nc := range chans {
					go b.handleChannel(ctx, &nop, targetConn, nc)
				}
			}()
		}
	}()

	return ln.Addr().String(), func() { ln.Close(); targetConn.Close() }
}

func dialClient(t *testing.T, bastionAddr string) *ssh.Client {
	t.Helper()
	c, err := ssh.Dial("tcp", bastionAddr, &ssh.ClientConfig{
		User:            "client",
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
		Timeout:         5 * time.Second,
	})
	if err != nil {
		t.Fatalf("dial bastion: %v", err)
	}
	return c
}

// exec with an already-closed (empty) stdin — the exact trigger of the old bug:
// the client half-closes stdin immediately, and we must still get the guest's
// output back.
func TestHandleChannel_ExecEmptyStdin(t *testing.T) {
	gAddr, gStop := startGuest(t)
	defer gStop()
	bAddr, bStop := startBastion(t, gAddr)
	defer bStop()

	client := dialClient(t, bAddr)
	defer client.Close()

	sess, err := client.NewSession()
	if err != nil {
		t.Fatalf("new session: %v", err)
	}
	defer sess.Close()
	sess.Stdin = strings.NewReader("") // immediate EOF

	out, err := sess.Output("hello")
	if err != nil {
		t.Fatalf("exec failed (regression: channel torn down on stdin EOF): %v", err)
	}
	if got := string(out); got != "GOT:" {
		t.Fatalf("exec output = %q, want %q", got, "GOT:")
	}
}

// exec with piped stdin — the guest must receive the payload and reply after EOF.
func TestHandleChannel_ExecPipedStdin(t *testing.T) {
	gAddr, gStop := startGuest(t)
	defer gStop()
	bAddr, bStop := startBastion(t, gAddr)
	defer bStop()

	client := dialClient(t, bAddr)
	defer client.Close()

	sess, err := client.NewSession()
	if err != nil {
		t.Fatalf("new session: %v", err)
	}
	defer sess.Close()
	sess.Stdin = strings.NewReader("payload-123")

	out, err := sess.Output("cmd")
	if err != nil {
		t.Fatalf("exec w/ stdin failed: %v", err)
	}
	if got := string(out); got != "GOT:payload-123" {
		t.Fatalf("exec output = %q, want %q", got, "GOT:payload-123")
	}
}

// stderr (SSH extended data) must reach the client's stderr, separate from stdout.
func TestHandleChannel_StderrForwarded(t *testing.T) {
	gAddr, gStop := startGuest(t)
	defer gStop()
	bAddr, bStop := startBastion(t, gAddr)
	defer bStop()

	client := dialClient(t, bAddr)
	defer client.Close()

	sess, err := client.NewSession()
	if err != nil {
		t.Fatalf("new session: %v", err)
	}
	defer sess.Close()
	sess.Stdin = strings.NewReader("")
	var errBuf strings.Builder
	sess.Stderr = &errBuf

	out, err := sess.Output("boom")
	if err != nil {
		t.Fatalf("exec failed: %v", err)
	}
	if got := string(out); got != "GOT:" {
		t.Fatalf("stdout = %q, want %q", got, "GOT:")
	}
	if got := errBuf.String(); got != "ERR:boom" {
		t.Fatalf("stderr = %q, want %q", got, "ERR:boom")
	}
}

// exit-status must propagate through the proxy (client sees a clean exit or the
// exact non-zero code, never "exited without exit status").
func TestHandleChannel_ExitStatusPropagates(t *testing.T) {
	gAddr, gStop := startGuest(t)
	defer gStop()
	bAddr, bStop := startBastion(t, gAddr)
	defer bStop()

	client := dialClient(t, bAddr)
	defer client.Close()

	// success path
	s0, _ := client.NewSession()
	s0.Stdin = strings.NewReader("")
	if err := s0.Run("ok"); err != nil {
		t.Fatalf("expected clean exit, got %v", err)
	}
	s0.Close()

	// non-zero path
	s7, _ := client.NewSession()
	s7.Stdin = strings.NewReader("")
	err := s7.Run("exit7")
	exitErr, ok := err.(*ssh.ExitError)
	if !ok {
		t.Fatalf("expected *ssh.ExitError, got %T (%v)", err, err)
	}
	if exitErr.ExitStatus() != 7 {
		t.Fatalf("exit status = %d, want 7", exitErr.ExitStatus())
	}
	s7.Close()
}
