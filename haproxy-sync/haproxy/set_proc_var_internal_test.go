package haproxy

import (
	"net"
	"path/filepath"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// recordingHAProxy answers every command with reply and records what it was
// asked, so the tests below can assert the exact bytes put on the admin socket.
func recordingHAProxy(t *testing.T, reply string) (string, func() string) {
	t.Helper()

	path := filepath.Join(t.TempDir(), "haproxy.sock")
	ln, err := net.Listen("unix", path)
	require.NoError(t, err)
	t.Cleanup(func() { _ = ln.Close() })

	received := make(chan string, 8)

	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			buf := make([]byte, 4096)
			_ = conn.SetReadDeadline(time.Now().Add(time.Second))
			n, _ := conn.Read(buf)
			received <- string(buf[:n])
			_, _ = conn.Write([]byte(reply))
			_ = conn.Close()
		}
	}()

	last := func() string {
		select {
		case got := <-received:
			return got
		case <-time.After(2 * time.Second):
			t.Fatal("haproxy stub received no command")
			return ""
		}
	}

	return path, last
}

func newTestHAProxy(path string) *HAProxy {
	logger := zerolog.Nop()
	return NewHAProxy(&logger, path)
}

// TestSetProcVarCommand pins the exact command, which is not obvious and was
// got wrong twice before being checked against a running HAProxy 3.3.
//
//   - `set var` is gated behind experimental mode, and that mode is per
//     CONNECTION, so enabling it has to ride on the same command string;
//     sending it separately silently leaves the variable unset.
//   - the value has to be `str(<v>)`. `str <v>` is rejected with "arg type must
//     be either 'expr' or 'fmt'".
func TestSetProcVarCommand(t *testing.T) {
	t.Parallel()

	path, lastCommand := recordingHAProxy(t, "")
	h := newTestHAProxy(path)

	require.NoError(t, h.SetProcVar("proc.acme_thumbprint", "abc123_-XYZ"))

	got := lastCommand()
	assert.Contains(t, got, "experimental-mode on")
	assert.Contains(t, got, "set var proc.acme_thumbprint str(abc123_-XYZ)")
	assert.Contains(t, got, ";", "experimental mode must ride on the same connection")
}

func TestSetProcVarAcceptsAnEmptyValue(t *testing.T) {
	t.Parallel()

	path, lastCommand := recordingHAProxy(t, "")
	h := newTestHAProxy(path)

	// An install with no ACME account has an empty thumbprint file, and
	// pushing that empty value is how the variable stays in step with it.
	require.NoError(t, h.SetProcVar("proc.acme_thumbprint", ""))
	assert.Contains(t, lastCommand(), "set var proc.acme_thumbprint str()")
}

func TestSetProcVarReportsAnHAProxyError(t *testing.T) {
	t.Parallel()

	path, _ := recordingHAProxy(t, "This command is restricted to experimental mode only.\n")
	h := newTestHAProxy(path)

	err := h.SetProcVar("proc.acme_thumbprint", "abc")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "experimental mode")
}

// TestSetProcVarRejectsNonProcessVariables: HAProxy only accepts proc-scoped
// names here, and a name it rejects would fail at the far end with a message
// nobody reads.
func TestSetProcVarRejectsNonProcessVariables(t *testing.T) {
	t.Parallel()

	path, _ := recordingHAProxy(t, "")
	h := newTestHAProxy(path)

	err := h.SetProcVar("txn.something", "abc")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "proc.")
}

// TestSetProcVarRejectsUnsafeValues: the value is interpolated into a command
// string on a control socket, and it comes from a file written by acme.sh from
// certificate-authority output. A thumbprint is base64url, so anything that
// could close the str(...) call or start a second command is refused rather
// than sent.
func TestSetProcVarRejectsUnsafeValues(t *testing.T) {
	t.Parallel()

	path, _ := recordingHAProxy(t, "")
	h := newTestHAProxy(path)

	for _, value := range []string{
		"abc)",
		"abc; shutdown",
		"abc\nshutdown",
		"abc def",
		"abc$(id)",
	} {
		assert.Error(t, h.SetProcVar("proc.acme_thumbprint", value), "value %q", value)
	}
}
