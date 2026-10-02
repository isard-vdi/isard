package protocol

import (
	"bytes"
	"context"
	"encoding/binary"
	"errors"
	"io"
	"net"
	"strconv"
	"sync"
	"testing"
	"time"
)

type pipeTransport struct {
	in   chan []byte
	out  chan []byte
	once sync.Once
	done chan struct{}
}

func newPipeTransport() *pipeTransport {
	return &pipeTransport{in: make(chan []byte, 16), out: make(chan []byte, 16), done: make(chan struct{})}
}

func (p *pipeTransport) ReadPacket() (int, []byte, error) {
	select {
	case b := <-p.in:
		return len(b), b, nil
	case <-p.done:
		return 0, nil, io.EOF
	}
}

func (p *pipeTransport) WritePacket(b []byte) (int, error) {
	select {
	case p.out <- append([]byte(nil), b...):
		return len(b), nil
	case <-p.done:
		return 0, io.ErrClosedPipe
	}
}

func (p *pipeTransport) Close() error {
	p.once.Do(func() { close(p.done) })
	return nil
}

// impatientBackend drops a connection whose first bytes do not arrive within window.
func impatientBackend(t *testing.T, window time.Duration) (string, uint16, <-chan []byte) {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %s", err)
	}
	t.Cleanup(func() { ln.Close() })
	got := make(chan []byte, 1)
	go func() {
		conn, err := ln.Accept()
		if err != nil {
			return
		}
		t.Cleanup(func() { conn.Close() })
		conn.SetReadDeadline(time.Now().Add(window))
		buf := make([]byte, 64)
		n, err := conn.Read(buf)
		if err != nil {
			conn.Close()
			got <- nil
			return
		}
		conn.SetReadDeadline(time.Time{})
		conn.Write([]byte("pong"))
		got <- buf[:n]
	}()
	host, port, _ := net.SplitHostPort(ln.Addr().String())
	p, _ := strconv.Atoi(port)
	return host, uint16(p), got
}

func dataPacket(payload []byte) []byte {
	b := new(bytes.Buffer)
	binary.Write(b, binary.LittleEndian, uint16(len(payload)))
	b.Write(payload)
	return createPacket(PKT_TYPE_DATA, b.Bytes())
}

func openChannel(t *testing.T, tr *pipeTransport, host string, port uint16) <-chan error {
	t.Helper()
	s := NewServer(&SessionInfo{TransportIn: tr, TransportOut: tr}, &ServerConf{TokenAuth: true})
	errc := make(chan error, 1)
	go func() { errc <- s.Process(context.Background()) }()

	client := ClientConfig{PAAToken: "token", Name: "client", Server: host, Port: int(port)}
	steps := []struct {
		req  []byte
		resp int
	}{
		{client.handshakeRequest(), PKT_TYPE_HANDSHAKE_RESPONSE},
		{client.tunnelRequest(), PKT_TYPE_TUNNEL_RESPONSE},
		{client.tunnelAuthRequest(), PKT_TYPE_TUNNEL_AUTH_RESPONSE},
		{client.channelRequest(), PKT_TYPE_CHANNEL_RESPONSE},
	}
	for _, st := range steps {
		tr.in <- st.req
		select {
		case b := <-tr.out:
			if pt, _, _, _ := readHeader(b); int(pt) != st.resp {
				t.Fatalf("expected packet type %d, got %d", st.resp, pt)
			}
		case err := <-errc:
			t.Fatalf("gateway stopped before packet type %d: %v", st.resp, err)
		case <-time.After(5 * time.Second):
			t.Fatalf("timeout waiting for packet type %d", st.resp)
		}
	}
	return errc
}

func TestChannelReachesImpatientBackend(t *testing.T) {
	host, port, got := impatientBackend(t, 100*time.Millisecond)
	tr := newPipeTransport()
	defer tr.Close()
	openChannel(t, tr, host, port)

	time.Sleep(400 * time.Millisecond)
	tr.in <- dataPacket([]byte("x224"))

	select {
	case b := <-got:
		if string(b) != "x224" {
			t.Fatalf("backend dropped the connection before the first client data (got %q)", b)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("backend never received the client data")
	}

	select {
	case b := <-tr.out:
		pt, _, pkt, _ := readHeader(b)
		if pt != PKT_TYPE_DATA || !bytes.Contains(pkt, []byte("pong")) {
			t.Fatalf("expected the backend reply as data, got type %d %x", pt, pkt)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("the backend reply never reached the client")
	}
}

func TestUnreachableBackendEndsSession(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %s", err)
	}
	host, portStr, _ := net.SplitHostPort(ln.Addr().String())
	ln.Close()
	port, _ := strconv.Atoi(portStr)

	tr := newPipeTransport()
	defer tr.Close()
	s := NewServer(&SessionInfo{TransportIn: tr, TransportOut: tr}, &ServerConf{TokenAuth: true})
	errc := make(chan error, 1)
	go func() { errc <- s.Process(context.Background()) }()
	go func() {
		for range tr.out {
		}
	}()

	client := ClientConfig{PAAToken: "token", Name: "client", Server: host, Port: port}
	for _, req := range [][]byte{
		client.handshakeRequest(), client.tunnelRequest(), client.tunnelAuthRequest(),
		client.channelRequest(), dataPacket([]byte("x224")),
	} {
		select {
		case tr.in <- req:
		case <-tr.done:
		}
	}

	select {
	case err := <-errc:
		var opErr *net.OpError
		if !errors.As(err, &opErr) {
			t.Fatalf("expected a dial error, got %v", err)
		}
	case <-time.After(20 * time.Second):
		t.Fatal("the gateway did not end the session")
	}
}
