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

	"github.com/pires/go-proxyproto"
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

	// Create standard TCP listener
	standardListener, err := net.Listen("tcp", cfg.Addr())
	if err != nil {
		log.Fatal().Str("addr", cfg.Addr()).Msg("serve HTTP")
	}

	// Wrap with proxy protocol listener
	lis := &proxyproto.Listener{
		Listener: standardListener,
		// Optional: you can restrict which source IPs can send proxy headers:
		// Policy: func(upstream net.Addr) (proxyproto.Policy, error) {
		//     // Only allow proxy protocol from your HAProxy servers
		//     if strings.HasPrefix(upstream.String(), "10.0.0.") {
		//         return proxyproto.USE, nil
		//     }
		//     return proxyproto.IGNORE, nil
		// },
	}

	go func() {
		for {
			conn, err := lis.Accept()
			if err != nil {
				log.Error().Err(err).Msg("accept incoming connection")
				continue
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

	connLog := *b.log
	var remoteIP string
	var remotePort string
	if proxyConn, ok := conn.(*proxyproto.Conn); ok {
		if proxyConn.ProxyHeader() != nil {
			remoteConn := proxyConn.ProxyHeader().SourceAddr.String()
			remoteIP = remoteConn[:strings.LastIndex(remoteConn, ":")]
			remotePort = remoteConn[strings.LastIndex(remoteConn, ":")+1:]
			connLog = b.log.With().Str("remote_ip", remoteIP).Str("remote_port", remotePort).Logger()
		}
	}

	// Attempt to extract the taget ID from the TLS request
	hello, peeked, err := b.peekTlsHello(ctx, conn)
	if err != nil {
		var tlsErr tls.RecordHeaderError
		if !errors.As(err, &tlsErr) {
			connLog.Warn().Err(err).Msg("peek TLS hello")
			return
		}

		if tlsErr.Msg != "first record does not look like a TLS handshake" {
			connLog.Warn().Err(err).Msg("peek TLS hello")
			return
		}

		b.handleHTTP(ctx, conn, peeked, remoteIP, remotePort)
		return
	}

	b.handleHTTPS(ctx, conn, peeked, hello, remoteIP, remotePort)
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

func (b *bastion) extractTargetIDFromDB(ctx context.Context, host string) (string, error) {
	target := &model.Target{}

	if err := target.LoadFromDomain(ctx, b.db, host); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			b.log.Debug().Msg("target not found by domain")
			return "", db.ErrNotFound
		}

		b.log.Error().Err(err).Msg("load target from the DB")
		return "", fmt.Errorf("load target from the DB: %w", err)
	}

	return target.ID, nil
}

func (b *bastion) extractTargetIDAndURL(ctx context.Context, host string) (string, string, error) {
	targetLog := *b.log
	targetLog = targetLog.With().Str("target_host", host).Logger()

	// Remove port if present
	if strings.Contains(host, ":") {
		host = strings.Split(host, ":")[0]
	}

	// Try to get the target ID from the database
	targetID, err := b.extractTargetIDFromDB(ctx, host)
	if err == nil {
		targetLog.Debug().Str("target_id", targetID).Msg("target ID found in DB")
		return targetID, host, nil
	}

	// Get the target ID from the host
	h := strings.Split(host, ".")
	if len(h) < 3 {
		return "", "", errors.New("invalid target")
	}

	// build the target ID by joining the first 2 parts with a dash
	targetID = strings.Join(h[:2], "-")

	// check that the target ID is a valid UUID
	splitID := strings.Split(targetID, "-")
	if len(splitID) != 5 {
		targetLog.Debug().Str("target_id", targetID).Msg("invalid target ID format")
		return "", "", errors.New("invalid target ID format")
	}

	// build the base URL by joining all but the first part
	targetURL := strings.Join(h[2:], ".")

	// return the target ID and the base URL
	return targetID, targetURL, nil
}

// TODO: Send helpful messages to the client
func (b *bastion) handleHTTP(ctx context.Context, conn net.Conn, prevPeeked *bytes.Buffer, remoteIP string, remotePort string) {
	httpLog := *b.log
	httpLog = httpLog.With().Str("remote_ip", remoteIP).Str("remote_port", remotePort).Logger()
	// Recreate the previously peeked buffer
	prevBuf := io.MultiReader(prevPeeked, conn)

	// Write all the read bytes to the peeked buffer
	peeked := &bytes.Buffer{}
	buf := bufio.NewReader(io.TeeReader(prevBuf, peeked))

	// *b.log = b.log.With().Str("remote_ip", remoteIP).Str("remote_port", remotePort).Logger()
	r, err := http.ReadRequest(buf)
	if err != nil {
		httpLog.Error().Err(err).Msg("read HTTP request from TCP")
		return
	}

	targetID, targetURL, err := b.extractTargetIDAndURL(ctx, r.Host)
	httpLog = httpLog.With().Str("target_id", targetID).Str("target_domain", targetURL).Logger()
	if err != nil {
		httpLog.Debug().Msg("invalid target")
		return
	}

	b.handleProxy(ctx, conn, peeked, false, targetID, targetURL, remoteIP, remotePort)
}

func (b *bastion) handleHTTPS(ctx context.Context, conn net.Conn, peeked *bytes.Buffer, hello *tls.ClientHelloInfo, remoteIP string, remotePort string) {
	httpsLog := *b.log
	httpsLog = httpsLog.With().Str("remote_ip", remoteIP).Str("remote_port", remotePort).Logger()
	targetID, targetURL, err := b.extractTargetIDAndURL(ctx, hello.ServerName)
	if err != nil {
		httpsLog.Debug().Msg("invalid target")
		return
	}

	b.handleProxy(ctx, conn, peeked, true, targetID, targetURL, remoteIP, remotePort)
}

func (b *bastion) handleProxy(ctx context.Context, conn net.Conn, peeked *bytes.Buffer, https bool, targetID string, targetURL string, remoteIP string, remotePort string) {
	proxyLog := *b.log
	target := &model.Target{
		ID: targetID,
	}
	proxyLog = b.log.With().
		Str("remote_ip", remoteIP).
		Str("remote_port", remotePort).
		Str("target_id", targetID).
		Str("target_domain", targetURL).Logger()
	// Get the target from the DB and ensure is enabled
	if err := target.Load(ctx, b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			proxyLog.Debug().Msg("target not found")
			return
		}

		proxyLog.Error().Err(err).Msg("load target from the DB")
		return
	}

	if !target.HTTP.Enabled {
		proxyLog.Debug().Msg("HTTP target service not enabled")
		return
	}

	config := &model.Config{}

	if err := config.Load(ctx, b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			proxyLog.Error().Msg("config not found")
			return
		}

		proxyLog.Error().Err(err).Msg("load config from DB")
		return
	}

	if !config.Bastion.Enabled {
		proxyLog.Error().Msg("bastion not enabled in the config")
		return
	}

	// Load the user to load the category to check the base URL
	user := &model.User{
		ID: target.UserID,
	}
	proxyLog = proxyLog.With().Str("user_id", user.ID).Logger()
	if err := user.Load(ctx, b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			proxyLog.Error().Msg("user not found")
			return
		}

		proxyLog.Error().Err(err).Msg("load user from DB")
		return
	}

	// Load the category to check the base URL
	category := &model.Category{
		ID: user.CategoryID,
	}
	proxyLog = proxyLog.With().Str("category_id", category.ID).Logger()
	if err := category.Load(ctx, b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			proxyLog.Error().Msg("category not found")
			return
		}

		proxyLog.Error().Err(err).Msg("load category from DB")
		return
	}

	proxyLog = proxyLog.With().Str("category_domain", category.BastionDomain).Str("config_domain", config.Bastion.Domain).Logger()
	// Check if the category has a base URL.
	proxyLog.Debug().Msg("category base URL")

	if target.Domain != targetURL {
		switch category.BastionDomain {
		case "0":
			// If the category has a base URL set to false, block all connections
			proxyLog.Debug().Msg("bastion not enabled in this category")
			return

		case "":
			// If the category has a base URL set to null, check if the config base URL is set
			// if it's set to null, allow all connections no matter the base URL
			if config.Bastion.Domain != "" && config.Bastion.Domain != targetURL {
				proxyLog.Debug().Msg("config base URL does not match")
				return
			}

		default:
			// If the category has a base URL, check if it matches the base URL
			if category.BastionDomain != targetURL {
				proxyLog.Debug().Msg("category base URL does not match")
				return
			}
		}
	}

	// Load the desktop
	dktp := &model.Desktop{
		ID: target.DesktopID,
	}
	proxyLog = proxyLog.With().Str("desktop_id", dktp.ID).Logger()
	if err := dktp.Load(context.Background(), b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			proxyLog.Error().Msg("desktop not found")
			return
		}

		proxyLog.Error().Err(err).Msg("load desktop from DB")
		return
	}

	// Ensure the desktop is in a valid state
	if dktp.Status != "Started" {
		proxyLog.Debug().Msg("desktop is not started")
		return
	}

	// Get the desktop IP
	if dktp.Viewer == nil || dktp.Viewer.GuestIP == nil {
		proxyLog.Debug().Msg("desktop has no IP")
		return
	}

	// Create the target connection
	port := target.HTTP.HTTPPort
	if https {
		port = target.HTTP.HTTPSPort
	}
	// *b.log = b.log.With().
	// 	Str("target_ip", *dktp.Viewer.GuestIP).
	// 	Int("target_port", port).
	// 	Logger()
	targetConn, err := net.Dial("tcp", net.JoinHostPort(*dktp.Viewer.GuestIP, strconv.Itoa(port)))
	if err != nil {
		proxyLog.Error().Err(err).Msg("create the target connection")
		return
	}
	defer targetConn.Close()

	proxyLog.Info().Msg("connection established")

	// Replay the previously read bytes
	if _, err := peeked.WriteTo(targetConn); err != nil {
		proxyLog.Error().Err(err).Msg("replay the initial transfer bytes")
		return
	}

	// Bidirectional binary copying between the client and the target
	ioErr := transport.Proxy(targetConn, conn)

	// Wait for the proxying to finish
	for {
		select {
		case err := <-ioErr:
			if err != nil {
				proxyLog.Error().Err(err).Msg("io error")
			}
			return

		case <-ctx.Done():
			return
		}
	}
}
