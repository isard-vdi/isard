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
	log *zerolog.Logger
	db  r.QueryExecutor
}

func Serve(ctx context.Context, wg *sync.WaitGroup, log *zerolog.Logger, db r.QueryExecutor, cfg cfg.HTTP) {
	b := &bastion{
		log: log,
		db:  db,
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

func (b *bastion) extractTargetIDAndURL(host string) (string, string, error) {
	// Get the target ID from the host
	h := strings.Split(host, ".")
	if len(h) < 2 {
		return "", "", errors.New("invalid target")
	}

	// build the base URL by joining all but the first part
	targetURL := strings.Join(h[1:], ".")
	b.log.Debug().Str("target_url", targetURL).Msg("target base URL")

	// return the target ID and the base URL
	return h[0], targetURL, nil
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

	targetID, targetURL, err := b.extractTargetIDAndURL(r.Host)
	if err != nil {
		b.log.Error().Msg("invalid target")
		return
	}

	b.handleProxy(ctx, conn, peeked, false, targetID, targetURL)
}

func (b *bastion) handleHTTPS(ctx context.Context, conn net.Conn, peeked *bytes.Buffer, hello *tls.ClientHelloInfo) {
	targetID, targetURL, err := b.extractTargetIDAndURL(hello.ServerName)
	if err != nil {
		b.log.Error().Msg("invalid target")
		return
	}

	b.handleProxy(ctx, conn, peeked, true, targetID, targetURL)
}

func (b *bastion) handleProxy(ctx context.Context, conn net.Conn, peeked *bytes.Buffer, https bool, targetID string, targetURL string) {
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

	config := &model.Config{}

	if err := config.Load(ctx, b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			b.log.Error().Str("target", target.ID).Msg("config not found")
			return
		}

		b.log.Error().Str("target", target.ID).Err(err).Msg("load config from DB")
		return
	}

	if !config.Bastion.Enabled {
		b.log.Error().Str("target", target.ID).Msg("bastion not enabled in the config")
		return
	}

	// Load the user to load the category to check the base URL
	user := &model.User{
		ID: target.UserID,
	}

	if err := user.Load(ctx, b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			b.log.Error().Str("target", target.ID).Str("user", user.ID).Msg("user not found")
			return
		}

		b.log.Error().Str("target", target.ID).Str("user", user.ID).Err(err).Msg("load user from DB")
		return
	}

	// Load the category to check the base URL
	category := &model.Category{
		ID: user.CategoryID,
	}

	if err := category.Load(ctx, b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			b.log.Error().Str("target", target.ID).Str("category", category.ID).Msg("category not found")
			return
		}

		b.log.Error().Str("target", target.ID).Str("category", category.ID).Err(err).Msg("load category from DB")
		return
	}

	// Check if the category has a base URL.
	b.log.Debug().Str("target", target.ID).Str("category", category.ID).Str("recieved_url", targetURL).Str("category_base_url", category.BastionDomain).Msg("category base URL")

	switch category.BastionDomain {
	case "0":
		// If the category has a base URL set to false, block all connections
		b.log.Info().Str("target", target.ID).Str("category", category.ID).Msg("bastion not enabled in this category")
		return

	case "":
		// If the category has a base URL set to null, check if the config base URL is set
		// if it's set to null, allow all connections no matter the base URL
		if config.Bastion.Domain != "" && config.Bastion.Domain != targetURL {
			b.log.Error().Str("target", target.ID).Msg("config base URL does not match")
			return
		}

	default:
		// If the category has a base URL, check if it matches the base URL
		if category.BastionDomain != targetURL {
			b.log.Error().Str("target", target.ID).Str("category", category.ID).Msg("category base URL does not match")
			return
		}
	}
	b.log.Debug().Str("target", target.ID).Str("domain", targetURL).Msg("category base URL matches")

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
