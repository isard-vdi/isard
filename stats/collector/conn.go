package collector

import (
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"

	"github.com/rs/zerolog"
	"golang.org/x/crypto/ssh"
	"libvirt.org/go/libvirt"
)

// LibvirtPool wraps a read-only *libvirt.Connect with automatic reconnect on
// dropped-connection errors (hypervisor container restarts, libvirtd crashes).
// The previous design kept a single *libvirt.Connect for the lifetime of the
// stats process, so once isard-hypervisor restarted, every collector tick
// failed with "client socket is closed" until stats-go itself was restarted.
type LibvirtPool struct {
	mux  sync.Mutex
	conn *libvirt.Connect
	uri  string
	log  *zerolog.Logger
}

func NewLibvirtPool(uri string, log *zerolog.Logger) (*LibvirtPool, error) {
	conn, err := libvirt.NewConnectReadOnly(uri)
	if err != nil {
		return nil, err
	}
	return &LibvirtPool{conn: conn, uri: uri, log: log}, nil
}

// Use invokes fn with the live connection. If fn returns an error that looks
// like a dropped connection, the pool reconnects and invokes fn once more.
// Callers must not keep pointers obtained from fn past the return — any
// *libvirt.Domain handle, for instance, may be attached to a connection that
// the pool is about to replace.
func (p *LibvirtPool) Use(fn func(*libvirt.Connect) error) error {
	p.mux.Lock()
	defer p.mux.Unlock()
	err := fn(p.conn)
	if err == nil || !isLibvirtConnDead(err) {
		return err
	}
	p.log.Warn().Err(err).Msg("libvirt connection dead, reconnecting")
	// Dial the new connection BEFORE closing the old one. If dial fails we
	// must leave p.conn intact — closing it would leave a dangling
	// "invalid connection pointer" that fails every subsequent Use until a
	// future reconnect succeeds. Keeping the dead handle lets the next Use
	// hit the same dead-conn error and retry the reconnect cleanly.
	newConn, rerr := libvirt.NewConnectReadOnly(p.uri)
	if rerr != nil {
		p.log.Error().Err(rerr).Msg("libvirt reconnect failed")
		return err
	}
	if _, cerr := p.conn.Close(); cerr != nil {
		p.log.Debug().Err(cerr).Msg("closing dead libvirt connection")
	}
	p.conn = newConn
	p.log.Info().Msg("libvirt reconnected")
	return fn(p.conn)
}

func (p *LibvirtPool) Close() error {
	p.mux.Lock()
	defer p.mux.Unlock()
	_, err := p.conn.Close()
	return err
}

// isLibvirtConnDead matches the transport-level failures libvirt surfaces
// when the remote libvirtd has gone away. Substring match is unavoidable —
// libvirt-go does not expose a typed error for socket loss.
func isLibvirtConnDead(err error) bool {
	if err == nil {
		return false
	}
	s := err.Error()
	return strings.Contains(s, "client socket is closed") ||
		strings.Contains(s, "cannot connect to server") ||
		strings.Contains(s, "unable to connect to server") ||
		strings.Contains(s, "connection closed") ||
		strings.Contains(s, "connection reset") ||
		strings.Contains(s, "Broken pipe") ||
		strings.Contains(s, "invalid connection pointer")
}

// SSHPool wraps *ssh.Client with automatic reconnect when NewSession fails on
// a stale connection (hypervisor sshd restart, network blip). Same failure
// class as LibvirtPool: the previous code held a Dial()'d client for the
// lifetime of the process.
type SSHPool struct {
	mux    sync.Mutex
	client *ssh.Client
	addr   string
	cfg    *ssh.ClientConfig
	log    *zerolog.Logger
}

func NewSSHPool(addr string, cfg *ssh.ClientConfig, log *zerolog.Logger) (*SSHPool, error) {
	client, err := ssh.Dial("tcp", addr, cfg)
	if err != nil {
		return nil, err
	}
	return &SSHPool{client: client, addr: addr, cfg: cfg, log: log}, nil
}

// WithSession serializes SSH work on the pool, opens a fresh session, invokes
// fn with it, and closes the session on return. On session-create or fn-level
// errors indicating a dead connection, the pool redials and invokes fn once
// more on a new session.
func (p *SSHPool) WithSession(fn func(*ssh.Session) error) error {
	p.mux.Lock()
	defer p.mux.Unlock()
	err := p.runOnce(fn)
	if err == nil || !isSSHConnDead(err) {
		return err
	}
	p.log.Warn().Err(err).Msg("ssh connection dead, reconnecting")
	_ = p.client.Close()
	client, rerr := ssh.Dial("tcp", p.addr, p.cfg)
	if rerr != nil {
		p.log.Error().Err(rerr).Msg("ssh reconnect failed")
		return fmt.Errorf("ssh reconnect: %w (original: %v)", rerr, err)
	}
	p.client = client
	p.log.Info().Msg("ssh reconnected")
	return p.runOnce(fn)
}

func (p *SSHPool) runOnce(fn func(*ssh.Session) error) error {
	sess, err := p.client.NewSession()
	if err != nil {
		return err
	}
	defer sess.Close()
	return fn(sess)
}

func (p *SSHPool) Close() error {
	p.mux.Lock()
	defer p.mux.Unlock()
	return p.client.Close()
}

func isSSHConnDead(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, io.EOF) {
		return true
	}
	s := err.Error()
	return strings.Contains(s, "EOF") ||
		strings.Contains(s, "use of closed network connection") ||
		strings.Contains(s, "connection reset") ||
		strings.Contains(s, "broken pipe") ||
		strings.Contains(s, "connect: connection refused")
}
