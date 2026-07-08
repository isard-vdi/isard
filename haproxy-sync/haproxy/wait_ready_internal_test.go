package haproxy

import (
	"context"
	"net"
	"path/filepath"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
)

// serveFakeHAProxy answers every command on ln with a fake "show version" reply
// and closes the connection. It exits when ln is closed.
func serveFakeHAProxy(ln net.Listener) {
	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return // listener closed
			}

			// Drain the client's command before replying, then hang up.
			buf := make([]byte, 256)
			_ = conn.SetReadDeadline(time.Now().Add(time.Second))
			_, _ = conn.Read(buf)
			_, _ = conn.Write([]byte("HAProxy version 3.3.0-test\n"))
			_ = conn.Close()
		}
	}()
}

// TestWaitReady_SocketAppearsLate covers the startup race: the socket only
// appears after WaitReady has started, and WaitReady must still connect.
func TestWaitReady_SocketAppearsLate(t *testing.T) {
	t.Parallel()

	path := filepath.Join(t.TempDir(), "haproxy.sock")

	lnCh := make(chan net.Listener, 1)
	go func() {
		time.Sleep(300 * time.Millisecond)
		ln, err := net.Listen("unix", path)
		if err != nil {
			lnCh <- nil
			return
		}
		serveFakeHAProxy(ln)
		lnCh <- ln
	}()

	logger := zerolog.Nop()
	h := NewHAProxy(&logger, path)

	err := h.WaitReady(context.Background(), 5*time.Second)

	if ln := <-lnCh; ln != nil {
		ln.Close()
	}

	assert.NoError(t, err)
}

// TestWaitReady_Timeout asserts WaitReady gives up with an error when the socket
// never becomes ready.
func TestWaitReady_Timeout(t *testing.T) {
	t.Parallel()

	path := filepath.Join(t.TempDir(), "nonexistent.sock")

	logger := zerolog.Nop()
	h := NewHAProxy(&logger, path)

	err := h.WaitReady(context.Background(), 200*time.Millisecond)

	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not ready")
}

// TestWaitReady_ContextCancel asserts WaitReady returns promptly when ctx is
// cancelled instead of blocking for the full timeout.
func TestWaitReady_ContextCancel(t *testing.T) {
	t.Parallel()

	path := filepath.Join(t.TempDir(), "nonexistent.sock")

	logger := zerolog.Nop()
	h := NewHAProxy(&logger, path)

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(50 * time.Millisecond)
		cancel()
	}()

	start := time.Now()
	err := h.WaitReady(ctx, 30*time.Second)
	elapsed := time.Since(start)

	assert.ErrorIs(t, err, context.Canceled)
	assert.True(t, elapsed < 2*time.Second, "WaitReady should return promptly on cancel, took %s", elapsed)
}
