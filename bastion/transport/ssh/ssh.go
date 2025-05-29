package ssh

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net"
	"regexp"
	"strconv"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/bastion/cfg"
	"gitlab.com/isard/isardvdi/bastion/model"
	"gitlab.com/isard/isardvdi/bastion/transport"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/pires/go-proxyproto"
	"github.com/rs/zerolog"
	"golang.org/x/crypto/ssh"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

// basic UUID regex: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
var uuidRegex = regexp.MustCompile("^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$")

const ExtensionTargetID = "target_id"
const ExtensionDesktopID = "desktop_id"

type bastion struct {
	log     *zerolog.Logger
	db      r.QueryExecutor
	privKey ssh.Signer
}

type conn struct {
	tcpConn    net.Conn
	srvConn    *ssh.ServerConn
	targetConn *ssh.Client
}

func Serve(ctx context.Context, wg *sync.WaitGroup, log *zerolog.Logger, db r.QueryExecutor, cfg cfg.SSH) {
	// Get the SSH private key
	privKey, err := initKey(cfg.PrivateKeyPath, cfg.PrivateKeySize)
	if err != nil {
		log.Fatal().Err(err).Msg("initialize SSH private key")
	}

	b := &bastion{
		log:     log,
		db:      db,
		privKey: privKey,
	}

	log.Info().Str("addr", cfg.Addr()).Msg("listening for SSH connections")

	// Create standard TCP listener
	standardListener, err := net.Listen("tcp", cfg.Addr())
	if err != nil {
		log.Fatal().Str("addr", cfg.Addr()).Msg("serve SSH")
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

	// Start accepting connections
	go func() {
		for {
			conn, err := lis.Accept()
			if err != nil {
				log.Error().Err(err).Msg("accept incoming connection")
				continue
			}

			// Now conn.RemoteAddr() will be the original client's address
			go b.handleConn(ctx, log, conn)
		}
	}()

	<-ctx.Done()

	lis.Close()
	wg.Done()
}

func (b *bastion) handleAuth(conn ssh.ConnMetadata, key ssh.PublicKey) (*ssh.Permissions, error) {
	// Check if targetID looks like a UUID
	if !uuidRegex.MatchString(conn.User()) {
		b.log.Warn().Str("target_id", conn.User()).Str("remote_addr", conn.RemoteAddr().String()).Msg("bannerCallback: non-UUID username received, applying delay")

		// Tarpit for non-UUID usernames
		time.Sleep(10 * time.Second) // Tarpit delay (e.g., 10 seconds)

		// Return a generic, non-informative banner after the delay.
		return nil, &ssh.BannerError{
			Message: "authentication failed.\n",
		}
	}

	// Get the target ID from the SSH user
	target := &model.Target{
		ID: conn.User(),
	}

	// Get the target from the DB and ensure is enabled
	if err := target.Load(context.Background(), b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			b.log.Error().Str("target", target.ID).Msg("target not found")
			return nil, &ssh.BannerError{
				Message: "authentication failed\n",
			}
		}

		b.log.Error().Str("target", target.ID).Err(err).Msg("load target from DB")
		return nil, &ssh.BannerError{
			Message: "service not available\n",
		}
	}

	if !target.SSH.Enabled {
		b.log.Error().Str("target", target.ID).Str("desktop", target.DesktopID).Msg("ssh transport disabled for target")

		return nil, &ssh.BannerError{
			Message: "SSH is not enabled for this target\n",
		}
	}

	// Authenticate the user with their SSH key against the authorized ones
	found := false
	for _, a := range target.SSH.AuthorizedKeys {
		aKey, _, _, _, err := ssh.ParseAuthorizedKey([]byte(a))
		if err != nil {
			// b.log.Warn().Str("target", target.ID).Str("desktop", target.DesktopID).Msg("parse SSH authorized key")
			continue
		}

		if bytes.Equal(ssh.MarshalAuthorizedKey(key), ssh.MarshalAuthorizedKey(aKey)) {
			found = true
			break
		}
	}

	if !found {
		b.log.Error().Str("target", target.ID).Str("desktop", target.DesktopID).Msg("key authentication failed, no matching valid keys")

		return nil, &ssh.BannerError{
			Message: "key authentication failed. Ensure you've correctly added your authorized_key(s) to this desktop bastion in IsardVDI\n",
		}
	}

	// Load the desktop
	dktp := &model.Desktop{
		ID: target.DesktopID,
	}

	if err := dktp.Load(context.Background(), b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			b.log.Error().Str("target", target.ID).Str("desktop", dktp.ID).Msg("desktop not found")
			return nil, &ssh.BannerError{
				Message: "destkop not found\n",
			}
		}

		b.log.Error().Str("target", target.ID).Str("desktop", dktp.ID).Err(err).Msg("load desktop from DB")
		return nil, &ssh.BannerError{
			Message: "service not available\n",
		}
	}

	// Ensure the desktop is in a valid state
	if dktp.Status != "Started" {
		b.log.Error().Str("target", target.ID).Str("desktop", dktp.ID).Msg("desktop not started")
		return nil, &ssh.BannerError{
			Message: "Desktop not started. Ensure it's started in IsardVDI\n",
		}
	}

	// Ensure the desktop has credentials
	if dktp.GuestProperties.Credentials.Username == "" || dktp.GuestProperties.Credentials.Password == "" {
		b.log.Error().Str("target", target.ID).Str("desktop", dktp.ID).Msg("desktop has no credentials")
		return nil, &ssh.BannerError{
			Message: "Desktop has no credentials set. Ensure desktop user/password was set for this desktop\n",
		}
	}

	// Get the desktop IP
	if dktp.Viewer == nil || dktp.Viewer.GuestIP == nil {
		b.log.Error().Str("target", target.ID).Str("desktop", dktp.ID).Msg("desktop has no ip")
		return nil, &ssh.BannerError{
			Message: "Desktop has no IP assigned yet. Ensure it has the WireGuard interface and wait till it's being assigned\n",
		}
	}

	return &ssh.Permissions{
		Extensions: map[string]string{
			ExtensionRemoteUsr:        dktp.GuestProperties.Credentials.Username,
			ExtensionRemotePwd:        dktp.GuestProperties.Credentials.Password,
			ExtensionRemoteTargetHost: *dktp.Viewer.GuestIP,
			ExtensionRemoteTargetPort: strconv.Itoa(target.SSH.Port),
			ExtensionTargetID:         target.ID,
			ExtensionDesktopID:        dktp.ID,
		},
	}, nil
}

func (b *bastion) handleConn(ctx context.Context, log *zerolog.Logger, tcpConn net.Conn) {
	defer tcpConn.Close()

	cfg := &ssh.ServerConfig{
		PublicKeyCallback: b.handleAuth,
		BannerCallback:    b.bannerCallback,
	}
	cfg.AddHostKey(b.privKey)

	// Accept the incoming SSH connection
	srvConn, chans, reqs, err := ssh.NewServerConn(tcpConn, cfg)
	if err != nil {
		// log.Error().Err(err).Msg("create ssh connection")
		return
	}
	defer srvConn.Close()

	*log = log.With().Str("remote_addr", srvConn.RemoteAddr().String()).Logger()
	log.Debug().Msg("accepted SSH connection")

	targetAddr := fmt.Sprintf("%s:%s",
		srvConn.Permissions.Extensions[ExtensionRemoteTargetHost],
		srvConn.Permissions.Extensions[ExtensionRemoteTargetPort],
	)

	*log = log.With().Str("target_addr", targetAddr).Logger()

	// Create the target SSH connection
	targetConn, err := ssh.Dial("tcp", targetAddr, &ssh.ClientConfig{
		User:            srvConn.Permissions.Extensions[ExtensionRemoteUsr],
		Auth:            []ssh.AuthMethod{ssh.Password(srvConn.Permissions.Extensions[ExtensionRemotePwd])},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
		Timeout:         5 * time.Second,
	})

	if err != nil {
		log.Error().Err(err).Msg("establish SSH proxy client connection")

		// Handle connection channels specifically for sending error messages
		go b.handleErrorChannels(ctx, log, chans, fmt.Sprintf(
			"Error connecting to target host: %s\r\n\r\nPlease check if the target VM is running and has SSH enabled.\r\n",
			err.Error(),
		))

		// Handle global requests to prevent client from hanging
		go b.handleEmptyRequests(ctx, reqs)

		// Wait a moment to ensure error message gets sent before connection closes
		select {
		case <-time.After(2 * time.Second):
		case <-ctx.Done():
		}

		return
	}
	defer targetConn.Close()

	targetID := srvConn.Permissions.Extensions[ExtensionTargetID]
	desktopID := srvConn.Permissions.Extensions[ExtensionDesktopID]
	b.log.Info().Str("target", targetID).Str("desktop", desktopID).Msg("connection stablished")

	// Start proxying
	go b.handleRequests(ctx, log, targetConn, reqs)
	b.handleChannels(ctx, log, targetConn, chans)
}

// handleErrorChannels accepts channels but only to display an error message
func (b *bastion) handleErrorChannels(ctx context.Context, log *zerolog.Logger, chans <-chan ssh.NewChannel, errorMsg string) {
	for {
		select {
		case newChan := <-chans:
			if newChan == nil {
				return
			}

			if newChan.ChannelType() != "session" {
				newChan.Reject(ssh.UnknownChannelType, "only session channels are supported")
				continue
			}

			// Accept the channel
			channel, requests, err := newChan.Accept()
			if err != nil {
				log.Error().Err(err).Msg("accept error notification channel")
				return
			}
			defer channel.Close()

			// Send the error message
			_, err = channel.Write([]byte(errorMsg))
			if err != nil {
				log.Error().Err(err).Msg("write error message to channel")
			}

			// Handle requests to prevent client hanging
			go func() {
				for req := range requests {
					if req.WantReply {
						req.Reply(false, nil)
					}
				}
			}()

			// Send exit status after showing the message
			_, err = channel.SendRequest("exit-status", false, ssh.Marshal(struct{ Status uint32 }{Status: 1}))
			if err != nil {
				log.Error().Err(err).Msg("send exit status")
			}

			return

		case <-ctx.Done():
			return
		}
	}
}

// handleEmptyRequests responds to SSH requests with failure to prevent client from hanging
func (b *bastion) handleEmptyRequests(ctx context.Context, reqs <-chan *ssh.Request) {
	for {
		select {
		case req := <-reqs:
			if req == nil {
				return
			}
			if req.WantReply {
				req.Reply(false, nil)
			}
		case <-ctx.Done():
			return
		}
	}
}

func (b *bastion) handleRequests(ctx context.Context, log *zerolog.Logger, targetConn *ssh.Client, reqs <-chan *ssh.Request) {
	for {
		select {
		case req := <-reqs:
			if req == nil {
				return
			}

			ok, payload, err := targetConn.SendRequest(req.Type, req.WantReply, req.Payload)
			if err != nil {
				log.Error().Err(err).Msg("send client request")
				return
			}

			if err := req.Reply(ok, payload); err != nil {
				log.Error().Err(err).Msg("reply client request")
				return
			}

		case <-ctx.Done():
			return

		default:
			if targetConn == nil {
				return
			}
		}
	}
}

func (b *bastion) handleChannels(ctx context.Context, log *zerolog.Logger, targetConn *ssh.Client, chans <-chan ssh.NewChannel) {
	for {
		select {
		case newChan := <-chans:
			if newChan == nil {
				return
			}

			go b.handleChannel(ctx, log, targetConn, newChan)

		case <-ctx.Done():
			return

		default:
			if targetConn == nil {
				return
			}
		}
	}
}

func (b *bastion) handleChannel(ctx context.Context, log *zerolog.Logger, targetConn *ssh.Client, newChan ssh.NewChannel) {
	// Accept the channel creation
	cliChan, cliReq, err := newChan.Accept()
	if err != nil {
		log.Error().Err(err).Msg("accept SSH server session")
		return
	}
	defer cliChan.Close()

	// Create the channel on the target
	targetChan, targetReq, err := targetConn.OpenChannel(newChan.ChannelType(), newChan.ExtraData())
	if err != nil {
		log.Error().Err(err).Msg("open SSH client channel")
		return
	}
	defer targetChan.Close()

	// Bidirectional binary copying between the client and the target
	ioErr := transport.Proxy(targetChan, cliChan)

	// Handle SSH events
	for {
		select {
		case req := <-cliReq:
			if req == nil {
				return
			}

			ok, err := targetChan.SendRequest(req.Type, req.WantReply, req.Payload)
			if err != nil {
				log.Error().Err(err).Msg("send client channel request")
				return
			}

			if err := req.Reply(ok, nil); err != nil {
				log.Error().Err(err).Msg("reply client channel request")
			}

		case req := <-targetReq:
			if req == nil {
				return
			}

			ok, err := cliChan.SendRequest(req.Type, req.WantReply, req.Payload)
			if err != nil {
				log.Error().Err(err).Msg("send client channel request")
				return
			}

			if err := req.Reply(ok, nil); err != nil {
				log.Error().Err(err).Msg("reply client channel request")
			}

		case err := <-ioErr:
			if err != nil {
				log.Error().Err(err).Msg("io error")
			}
			return

		case <-ctx.Done():
			return

		default:
			if targetConn == nil {
				return
			}
		}
	}
}

func (b *bastion) bannerCallback(_ ssh.ConnMetadata) string {
	return `
You are using IsardVDI.

(_(
/_/'_____/)
"  |      |
   |""""""|
   
Enjoy.

`
}
