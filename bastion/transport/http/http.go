package http

import (
	"bufio"
	"bytes"
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"strconv"
	"strings"
	"sync"

	"gitlab.com/isard/isardvdi/bastion/cfg"
	"gitlab.com/isard/isardvdi/bastion/model"
	"gitlab.com/isard/isardvdi/bastion/transport"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type bastion struct {
	log     *zerolog.Logger
	db      r.QueryExecutor
	baseURL string
}

func Serve(ctx context.Context, wg *sync.WaitGroup, log *zerolog.Logger, db r.QueryExecutor, cfg cfg.HTTP) {
	b := &bastion{
		log:     log,
		db:      db,
		baseURL: cfg.BaseURL,
	}

	log.Info().Str("addr", cfg.Addr()).Msg("listening for HTTP connections")
	lis, err := net.Listen("tcp", cfg.Addr())
	if err != nil {
		log.Fatal().Str("addr", cfg.Addr()).Msg("serve HTTP")
	}

	go func() {
		for {
			conn, err := lis.Accept()
			if err != nil {
				log.Error().Err(err).Msg("accept incoming connection")
			}

			go b.handleConn(ctx, conn)
		}
	}()

	<-ctx.Done()

	lis.Close()
	wg.Done()
}

func (b *bastion) handleConn(ctx context.Context, conn net.Conn) {
	defer conn.Close()

	// Attempt to extract the taget ID from the TLS request
	hello, peeked, err := b.peekTlsHello(ctx, conn)
	if err != nil {
		var tlsErr tls.RecordHeaderError
		if !errors.As(err, &tlsErr) {
			b.log.Error().Err(err).Msg("peek TLS hello")
			return
		}

		if tlsErr.Msg != "first record does not look like a TLS handshake" {
			b.log.Error().Err(err).Msg("peek TLS hello")
			return
		}

		b.handleHTTP(ctx, conn, peeked)
		return
	}

	b.handleHTTPS(ctx, conn, peeked, hello)
}

func (b *bastion) peekTlsHello(ctx context.Context, conn net.Conn) (*tls.ClientHelloInfo, *bytes.Buffer, error) {
	peeked := &bytes.Buffer{}
	roConn := transport.ReadOnlyConn{
		Reader: io.TeeReader(conn, peeked),
	}

	var hello *tls.ClientHelloInfo
	err := tls.Server(roConn, &tls.Config{
		GetConfigForClient: func(info *tls.ClientHelloInfo) (*tls.Config, error) {
			hello = info
			return nil, nil
		},
	}).HandshakeContext(ctx)
	if hello == nil {
		return nil, peeked, fmt.Errorf("TLS handshake: %w", err)
	}

	return hello, peeked, nil
}

func (b *bastion) extractTargetID(host string) (string, error) {
	// Get the target ID from the host
	h := strings.Split(host, b.baseURL)
	if len(h) != 2 || len(h[0]) <= 1 {
		return "", errors.New("invalid target")
	}

	// Remove the final . from the subdomain
	return h[0][:len(h[0])-1], nil
}

// TODO: Send helpful messages to the client
func (b *bastion) handleHTTP(ctx context.Context, conn net.Conn, prevPeeked *bytes.Buffer) {
	// Recreate the previously peeked buffer
	prevBuf := io.MultiReader(prevPeeked, conn)

	// Write all the read bytes to the peeked buffer
	peeked := &bytes.Buffer{}
	buf := bufio.NewReader(io.TeeReader(prevBuf, peeked))

	r, err := http.ReadRequest(buf)
	if err != nil {
		b.log.Error().Err(err).Msg("read HTTP request from TCP")
		return
	}

	targetID, err := b.extractTargetID(r.Host)
	if err != nil {
		b.log.Error().Msg("invalid target")
		return
	}

	b.handleProxy(ctx, conn, peeked, false, targetID)
}

func (b *bastion) handleHTTPS(ctx context.Context, conn net.Conn, peeked *bytes.Buffer, hello *tls.ClientHelloInfo) {
	targetID, err := b.extractTargetID(hello.ServerName)
	if err != nil {
		b.log.Error().Msg("invalid target")
		return
	}

	b.handleProxy(ctx, conn, peeked, true, targetID)
}

func (b *bastion) handleProxy(ctx context.Context, conn net.Conn, peeked *bytes.Buffer, https bool, targetID string) {
	target := &model.Target{
		ID: targetID,
	}

	// Get the target from the DB and ensure is enabled
	if err := target.Load(ctx, b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			b.log.Error().Str("target", target.ID).Msg("target not found")
			return
		}

		b.log.Error().Str("target", target.ID).Err(err).Msg("load target from the DB")
		return
	}

	if !target.HTTP.Enabled {
		b.log.Error().Str("target", target.ID).Msg("HTTP target not enabled")
		return
	}

	// Load the desktop
	dktp := &model.Desktop{
		ID: target.DesktopID,
	}

	if err := dktp.Load(context.Background(), b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			b.log.Error().Str("target", target.ID).Str("desktop", dktp.ID).Msg("desktop not found")
			return
		}

		b.log.Error().Str("target", target.ID).Str("desktop", dktp.ID).Err(err).Msg("load desktop from DB")
		return
	}

	// Ensure the desktop is in a valid state
	if dktp.Status != "Started" {
		b.log.Error().Str("desktop", dktp.ID).Msg("desktop is not started")
		return
	}

	if dktp.Viewer == nil {
		b.log.Error().Str("desktop", dktp.ID).Msg("desktop has no viewer")
		return
	}

	// Get the desktop IP
	if dktp.Viewer.GuestIP == nil {
		b.log.Error().Str("desktop", dktp.ID).Msg("desktop has no ip")
		return
	}

	// Create the target connection
	port := target.HTTP.HTTPPort
	if https {
		port = target.HTTP.HTTPSPort
	}
	targetConn, err := net.Dial("tcp", net.JoinHostPort(*dktp.Viewer.GuestIP, strconv.Itoa(port)))
	if err != nil {
		b.log.Error().Err(err).Msg("create the target connection")
		return
	}
	defer targetConn.Close()

	b.log.Debug().Msg("created HTTP connection. Starting to proxy")

	// Replay the previously read bytes
	if _, err := peeked.WriteTo(targetConn); err != nil {
		b.log.Error().Err(err).Msg("replay the initial transfer bytes")
		return
	}

	// Bidirectional binary copying between the client and the target
	ioErr := transport.Proxy(targetConn, conn)

	// Wait for the proxying to finish
	for {
		select {
		case err := <-ioErr:
			if err != nil {
				b.log.Error().Err(err).Msg("io error")
			}
			return

		case <-ctx.Done():
			return
		}
	}
}
