package ssh

import (
	"bufio"
	"bytes"
	"context"
	"crypto/ed25519"
	"net"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/bastion/model"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"golang.org/x/crypto/ssh"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type lockedBuffer struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func (l *lockedBuffer) Write(p []byte) (int, error) {
	l.mu.Lock()
	defer l.mu.Unlock()

	return l.buf.Write(p)
}

func (l *lockedBuffer) lines() []string {
	l.mu.Lock()
	defer l.mu.Unlock()

	var out []string
	sc := bufio.NewScanner(bytes.NewReader(l.buf.Bytes()))
	sc.Buffer(make([]byte, 0, 64*1024), 16*1024*1024)
	for sc.Scan() {
		out = append(out, sc.Text())
	}

	return out
}

// newLoggerTestBastion points its only target at a closed port, so every connection logs on the dial-error path.
func newLoggerTestBastion(t *testing.T, targetID, desktopID string, key ssh.PublicKey, out *lockedBuffer) (*bastion, *zerolog.Logger) {
	t.Helper()

	closed, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	port := closed.Addr().(*net.TCPAddr).Port
	require.NoError(t, closed.Close())

	return newLoggerTestBastionOnPort(t, targetID, desktopID, key, out, port)
}

// newTargetSSHServer accepts the bastion's password login and then just holds the connection.
func newTargetSSHServer(t *testing.T) int {
	t.Helper()

	_, hostPriv, err := ed25519.GenerateKey(nil)
	require.NoError(t, err)
	hostKey, err := ssh.NewSignerFromKey(hostPriv)
	require.NoError(t, err)

	cfg := &ssh.ServerConfig{
		PasswordCallback: func(_ ssh.ConnMetadata, _ []byte) (*ssh.Permissions, error) {
			return nil, nil
		},
	}
	cfg.AddHostKey(hostKey)

	lis, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	t.Cleanup(func() { lis.Close() })

	go func() {
		for {
			conn, err := lis.Accept()
			if err != nil {
				return
			}

			go func() {
				defer conn.Close()

				srvConn, chans, reqs, err := ssh.NewServerConn(conn, cfg)
				if err != nil {
					return
				}
				defer srvConn.Close()

				go ssh.DiscardRequests(reqs)
				for newChan := range chans {
					_ = newChan.Reject(ssh.Prohibited, "test target")
				}
			}()
		}
	}()

	return lis.Addr().(*net.TCPAddr).Port
}

func newLoggerTestBastionOnPort(t *testing.T, targetID, desktopID string, key ssh.PublicKey, out *lockedBuffer, port int) (*bastion, *zerolog.Logger) {
	t.Helper()

	ip := "127.0.0.1"
	mock := r.NewMock()
	mock.On(r.Table("targets").Get(targetID)).Return([]any{
		map[string]any{
			"id":         targetID,
			"desktop_id": desktopID,
			"ssh": map[string]any{
				"enabled":         true,
				"port":            port,
				"authorized_keys": []string{string(ssh.MarshalAuthorizedKey(key))},
			},
		},
	}, nil)
	mock.On(r.Table("domains").Get(desktopID)).Return([]any{
		map[string]any{
			"id":     desktopID,
			"status": "Started",
			"guest_properties": map[string]any{
				"credentials": map[string]any{"username": "user", "password": "pass"},
			},
			"viewer": map[string]any{"guest_ip": ip},
		},
	}, nil)

	logger := zerolog.New(out)

	var wg sync.WaitGroup
	cfgWatcher := db.NewWatcher(&logger, time.Hour, 0, func(_ context.Context) (model.Config, error) {
		return model.Config{Bastion: model.Bastion{Enabled: true}}, nil
	})
	require.NoError(t, cfgWatcher.Start(t.Context(), &wg))

	_, hostPriv, err := ed25519.GenerateKey(nil)
	require.NoError(t, err)
	hostKey, err := ssh.NewSignerFromKey(hostPriv)
	require.NoError(t, err)

	return &bastion{log: &logger, db: mock, cfgWatcher: cfgWatcher, privKey: hostKey}, &logger
}

func dialThroughBastion(t *testing.T, b *bastion, log *zerolog.Logger, user string, signer ssh.Signer) {
	t.Helper()

	lis, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer lis.Close()

	done := make(chan struct{})
	go func() {
		defer close(done)

		conn, err := lis.Accept()
		if err != nil {
			return
		}

		b.handleConn(t.Context(), log, conn)
	}()

	client, err := ssh.Dial("tcp", lis.Addr().String(), &ssh.ClientConfig{
		User:            user,
		Auth:            []ssh.AuthMethod{ssh.PublicKeys(signer)},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(), //nolint:gosec // test-only host
		Timeout:         5 * time.Second,
	})
	require.NoError(t, err)
	// on the established path the bastion proxies until the client leaves
	require.NoError(t, client.Close())

	select {
	case <-done:
	case <-time.After(10 * time.Second):
		t.Fatal("the bastion did not finish handling the connection")
	}
}

func clientSigner(t *testing.T, seed byte) ssh.Signer {
	t.Helper()

	rawSeed := make([]byte, ed25519.SeedSize)
	for i := range rawSeed {
		rawSeed[i] = seed
	}

	signer, err := ssh.NewSignerFromKey(ed25519.NewKeyFromSeed(rawSeed))
	require.NoError(t, err)

	return signer
}

func TestHandleConnLoggerIsPerConnection(t *testing.T) {
	assert := assert.New(t)

	const (
		targetID  = "5054aaaa-0000-4000-8000-000000000001"
		desktopID = "desktop-5054-sequential"
	)

	signer := clientSigner(t, 54)
	out := &lockedBuffer{}
	b, shared := newLoggerTestBastion(t, targetID, desktopID, signer.PublicKey(), out)

	const conns = 3
	for range conns {
		dialThroughBastion(t, b, shared, targetID, signer)
	}

	var errLines []string
	for _, l := range out.lines() {
		if strings.Contains(l, "establish SSH proxy client connection") {
			errLines = append(errLines, l)
		}
	}
	require.Len(t, errLines, conns)

	for i, l := range errLines {
		assert.Equal(1, strings.Count(l, `"remote_addr"`), "connection %d: its line must carry only its own remote_addr", i+1)
		assert.Equal(1, strings.Count(l, `"target_addr"`), "connection %d: its line must carry only its own target_addr", i+1)
	}

	before := len(out.lines())
	shared.Info().Msg("probe after " + strconv.Itoa(conns) + " connections")
	probe := out.lines()[before]
	assert.NotContains(probe, "remote_addr")
	assert.NotContains(probe, "target_addr")
}

// Run with -race: concurrent connections must not write a shared logger.
func TestHandleConnConcurrentConnectionsDoNotShareLogger(t *testing.T) {
	const (
		targetID  = "5054aaaa-0000-4000-8000-000000000002"
		desktopID = "desktop-5054-concurrent"
	)

	signer := clientSigner(t, 55)
	out := &lockedBuffer{}
	b, shared := newLoggerTestBastion(t, targetID, desktopID, signer.PublicKey(), out)

	// Warm the target and desktop caches: the rethinkdb mock is not safe for concurrent queries.
	dialThroughBastion(t, b, shared, targetID, signer)

	var wg sync.WaitGroup
	for range 4 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			dialThroughBastion(t, b, shared, targetID, signer)
		}()
	}
	wg.Wait()

	for _, l := range out.lines() {
		if strings.Contains(l, "establish SSH proxy client connection") {
			assert.Equal(t, 1, strings.Count(l, `"remote_addr"`))
		}
	}
}

func TestHandleConnEstablishedLineCarriesItsOwnAddresses(t *testing.T) {
	assert := assert.New(t)

	const (
		targetID  = "5054aaaa-0000-4000-8000-000000000003"
		desktopID = "desktop-5054-established"
	)

	signer := clientSigner(t, 56)
	out := &lockedBuffer{}
	b, shared := newLoggerTestBastionOnPort(t, targetID, desktopID, signer.PublicKey(), out, newTargetSSHServer(t))

	const conns = 3
	for range conns {
		dialThroughBastion(t, b, shared, targetID, signer)
	}

	var established []string
	for _, l := range out.lines() {
		if strings.Contains(l, "connection stablished") {
			established = append(established, l)
		}
	}
	require.Len(t, established, conns)

	for i, l := range established {
		assert.Equal(1, strings.Count(l, `"remote_addr"`), "connection %d: the established line must say where it comes from, once", i+1)
		assert.Equal(1, strings.Count(l, `"target_addr"`), "connection %d: the established line must say where it goes, once", i+1)
	}
}
