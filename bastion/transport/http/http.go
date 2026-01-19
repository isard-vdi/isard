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
	"time"

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
	// Initial proxyLog setup
	protocol := "http"
	if https {
		protocol = "https"
	}
	baseLog := b.log.With().
		Str("protocol", protocol).
		Str("remote_ip", remoteIP).
		Str("remote_port", remotePort).
		Str("target_id", targetID).
		Str("target_domain", targetURL).Logger()

	baseLog.Info().Msg("handleProxy started")

	var originalPeekedData []byte
	if peeked != nil && peeked.Len() > 0 {
		originalPeekedData = make([]byte, peeked.Len())
		copy(originalPeekedData, peeked.Bytes())
	}

	maxAttempts := 3
	for attempt := 0; attempt < maxAttempts; attempt++ {
		proxyLog := baseLog.With().Int("attempt", attempt+1).Logger()

		if attempt > 0 {
			proxyLog.Info().Msg("Retrying target connection and proxying")
			select {
			case <-time.After(time.Duration(attempt) * 1 * time.Second):
			case <-ctx.Done():
				proxyLog.Info().Msg("Context cancelled during retry delay")
				return
			}
		}

		currentTarget := &model.Target{ID: targetID}
		if err := currentTarget.Load(ctx, b.db); err != nil {
			proxyLog.Error().Err(err).Msg("Failed to load target")
			if errors.Is(err, db.ErrNotFound) {
				return
			}
			if attempt == maxAttempts-1 {
				return
			}
			continue
		}
		proxyLog = proxyLog.With().Str("loaded_target_id", currentTarget.ID).Logger()

		if !currentTarget.HTTP.Enabled {
			proxyLog.Debug().Msg("HTTP target service not enabled for loaded target")
			return
		}

		currentConfig := &model.Config{}
		if err := currentConfig.Load(ctx, b.db); err != nil {
			proxyLog.Error().Err(err).Msg("Failed to load config")
			if errors.Is(err, db.ErrNotFound) {
				return
			}
			if attempt == maxAttempts-1 {
				return
			}
			continue
		}

		if !currentConfig.Bastion.Enabled {
			proxyLog.Error().Msg("Bastion not enabled in the config")
			return
		}

		currentUser := &model.User{ID: currentTarget.UserID}
		proxyLog = proxyLog.With().Str("user_id", currentUser.ID).Logger()
		if err := currentUser.Load(ctx, b.db); err != nil {
			proxyLog.Error().Err(err).Msg("Failed to load user")
			if errors.Is(err, db.ErrNotFound) {
				return
			}
			if attempt == maxAttempts-1 {
				return
			}
			continue
		}

		currentCategory := &model.Category{ID: currentUser.CategoryID}
		proxyLog = proxyLog.With().Str("category_id", currentCategory.ID).Logger()
		if err := currentCategory.Load(ctx, b.db); err != nil {
			proxyLog.Error().Err(err).Msg("Failed to load category")
			if errors.Is(err, db.ErrNotFound) {
				return
			}
			if attempt == maxAttempts-1 {
				return
			}
			continue
		}
		proxyLog = proxyLog.With().Str("category_ID", currentCategory.ID).Str("category_domain", currentCategory.BastionDomain).Str("config_domain", currentConfig.Bastion.Domain).Logger()

		if currentCategory.BastionDomain == "0" {
			proxyLog.Debug().Msg("Bastion disabled in category")
			return
		}

		if !currentTarget.HasDomain(targetURL) {
			switch currentCategory.BastionDomain {
			case "":
				if currentConfig.Bastion.Domain != "" && currentConfig.Bastion.Domain != targetURL {
					proxyLog.Debug().Str("expected_config_domain", currentConfig.Bastion.Domain).Msg("Config base URL does not match target URL")
					return
				}
			default:
				if currentCategory.BastionDomain != targetURL {
					proxyLog.Debug().Str("expected_category_domain", currentCategory.BastionDomain).Msg("Category base URL does not match target URL")
					return
				}
			}
		}

		currentDesktop := &model.Desktop{ID: currentTarget.DesktopID}
		proxyLog = proxyLog.With().Str("desktop_id", currentDesktop.ID).Logger()
		// Ensure ctx is used for loading desktop
		if err := currentDesktop.Load(ctx, b.db); err != nil {
			proxyLog.Error().Err(err).Msg("Failed to load desktop")
			if errors.Is(err, db.ErrNotFound) {
				return
			}
			if attempt == maxAttempts-1 {
				return
			}
			continue
		}

		if currentDesktop.Status != "Started" {
			proxyLog.Debug().Str("desktop_status", currentDesktop.Status).Msg("Desktop is not started")
			return
		}
		if currentDesktop.Viewer == nil || currentDesktop.Viewer.GuestIP == nil {
			proxyLog.Debug().Msg("Desktop has no IP")
			return
		}

		targetPort := currentTarget.HTTP.HTTPPort
		if https {
			targetPort = currentTarget.HTTP.HTTPSPort
		}
		targetAddr := net.JoinHostPort(*currentDesktop.Viewer.GuestIP, strconv.Itoa(targetPort))
		proxyLog.Info().Str("target_address", targetAddr).Msg("Attempting to dial target backend")

		// Use longer timeout for HTTPS connections
		dialTimeout := 10 * time.Second
		if https {
			dialTimeout = 30 * time.Second
			proxyLog.Debug().Msg("Using extended timeout for HTTPS connection")
		}

		targetConn, err := net.DialTimeout("tcp", targetAddr, dialTimeout)
		if err != nil {
			proxyLog.Error().Err(err).Str("target_address", targetAddr).Msg("Failed to create target connection")
			if attempt == maxAttempts-1 {
				proxyLog.Error().Msg("Max retry attempts reached for dialing target.")
				return
			}
			continue
		}
		proxyLog.Info().Str("local_addr_to_target", targetConn.LocalAddr().String()).Str("remote_addr_to_target", targetConn.RemoteAddr().String()).Msg("Connection to target established")

		// Send PROXY Protocol v2 header to forward real client IP to guest
		if remoteIP != "" && remotePort != "" {
			targetConn.SetWriteDeadline(time.Now().Add(5 * time.Second))
			if err := sendProxyProtocolV2(targetConn, remoteIP, remotePort, *currentDesktop.Viewer.GuestIP, targetPort); err != nil {
				proxyLog.Error().Err(err).Msg("Failed to send PROXY protocol v2 header")
				targetConn.Close()
				if attempt == maxAttempts-1 {
					return
				}
				continue
			}
			targetConn.SetWriteDeadline(time.Time{})
			proxyLog.Debug().Msg("Sent PROXY protocol v2 header to target")
		}

		// Always replay peeked data if available (not just on first attempt)
		if len(originalPeekedData) > 0 {
			proxyLog.Debug().Int("bytes_to_replay", len(originalPeekedData)).Msg("Replaying initial peeked bytes to target")

			// Set a write deadline for the initial data
			targetConn.SetWriteDeadline(time.Now().Add(5 * time.Second))
			if _, errWrite := targetConn.Write(originalPeekedData); errWrite != nil {
				proxyLog.Error().Err(errWrite).Msg("Failed to replay initial peeked bytes to target")
				targetConn.Close()
				if attempt == maxAttempts-1 {
					return
				}
				continue
			}
			// Clear the write deadline
			targetConn.SetWriteDeadline(time.Time{})
			proxyLog.Debug().Msg("Successfully replayed initial peeked bytes")
		}

		ioErrChan := transport.Proxy(targetConn, conn)
		connectionBroken := false

		proxyLog.Debug().Msg("Starting to monitor proxy io.Copy channels.")

		// Monitor proxy channels until they close or context is cancelled
		for {
			select {
			case errProxy, ok := <-ioErrChan:
				if !ok {
					// Channel closed - proxy monitoring completed
					proxyLog.Debug().Msg("Proxy ioErrChan closed - monitoring completed")
					goto endProxyLoop
				}

				if errProxy != nil {
					logMsg := proxyLog.Warn()
					if errors.Is(errProxy, io.EOF) {
						logMsg = proxyLog.Debug() // EOF is often normal
						logMsg.Err(errProxy).Msg("Proxy io.Copy finished with EOF")
					} else if errors.Is(errProxy, net.ErrClosed) {
						logMsg = proxyLog.Debug() // ErrClosed can also be normal if one side closes
						logMsg.Err(errProxy).Msg("Proxy io.Copy on a closed network connection")
					} else {
						// Any other error is more suspicious for an active session
						logMsg.Err(errProxy).Msg("Proxy io.Copy error during active session")
						connectionBroken = true
					}
				} else {
					proxyLog.Debug().Msg("Proxy io.Copy completed one direction cleanly (nil error)")
				}

			case <-ctx.Done():
				proxyLog.Info().Msg("Context done during proxying, terminating")
				targetConn.Close()
				return
			}
		}

	endProxyLoop: // Label to break out of the select/for proxy monitoring

		targetConn.Close()
		proxyLog.Debug().Msg("Finished monitoring proxy io.Copy channels")

		if connectionBroken {
			proxyLog.Warn().Msg("Connection to target was broken or an unexpected error occurred during proxying")

			// Verify the client connection is actually broken before retrying
			conn.SetWriteDeadline(time.Now().Add(1 * time.Second))
			if _, err := conn.Write([]byte{}); err != nil {
				proxyLog.Debug().Msg("Confirmed client connection is broken")
				if attempt == maxAttempts-1 {
					proxyLog.Error().Msg("Max retry attempts reached after connection broke")
					return
				}
				// Clear the write deadline before continuing
				conn.SetWriteDeadline(time.Time{})
			} else {
				proxyLog.Debug().Msg("Client connection seems healthy, not retrying")
				conn.SetWriteDeadline(time.Time{})
				return
			}
		} else {
			proxyLog.Info().Msg("Proxying finished (both directions completed or client closed gracefully)")
			return
		}
	}
	baseLog.Info().Msg("handleProxy finished after all attempts")
}

// sendProxyProtocolV2 sends a PROXY Protocol v2 header to the target connection
// to forward the real client IP address
func sendProxyProtocolV2(targetConn net.Conn, remoteIP string, remotePort string, destIP string, destPort int) error {
	srcPort, err := strconv.Atoi(remotePort)
	if err != nil {
		return fmt.Errorf("parse remote port: %w", err)
	}

	srcIP := net.ParseIP(remoteIP)
	if srcIP == nil {
		return fmt.Errorf("parse remote IP: %s", remoteIP)
	}

	dstIP := net.ParseIP(destIP)
	if dstIP == nil {
		return fmt.Errorf("parse destination IP: %s", destIP)
	}

	// Determine transport protocol based on IP version
	var transportProtocol proxyproto.AddressFamilyAndProtocol
	if srcIP.To4() != nil {
		transportProtocol = proxyproto.TCPv4
	} else {
		transportProtocol = proxyproto.TCPv6
	}

	header := &proxyproto.Header{
		Version:           2,
		Command:           proxyproto.PROXY,
		TransportProtocol: transportProtocol,
		SourceAddr: &net.TCPAddr{
			IP:   srcIP,
			Port: srcPort,
		},
		DestinationAddr: &net.TCPAddr{
			IP:   dstIP,
			Port: destPort,
		},
	}

	_, err = header.WriteTo(targetConn)
	if err != nil {
		return fmt.Errorf("write proxy protocol header: %w", err)
	}

	return nil
}
