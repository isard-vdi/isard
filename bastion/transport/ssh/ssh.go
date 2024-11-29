package ssh

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net"
	"strconv"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/bastion/cfg"
	"gitlab.com/isard/isardvdi/bastion/model"
	"gitlab.com/isard/isardvdi/bastion/transport"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/rs/zerolog"
	"golang.org/x/crypto/ssh"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

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
	lis, err := net.Listen("tcp", cfg.Addr())
	if err != nil {
		log.Fatal().Str("addr", cfg.Addr()).Msg("serve SSH")
	}

	// Start accepting connections
	go func() {
		for {
			conn, err := lis.Accept()
			if err != nil {
				log.Error().Err(err).Msg("accept incoming connection")
				continue
			}

			go b.handleConn(ctx, log, conn)
		}
	}()

	<-ctx.Done()

	lis.Close()
	wg.Done()
}

func (b *bastion) handleAuth(conn ssh.ConnMetadata, key ssh.PublicKey) (*ssh.Permissions, error) {
	// Get the target ID from the SSH user
	target := &model.Target{
		ID: conn.User(),
	}

	// Get the target from the DB and ensure is enabled
	if err := target.Load(context.Background(), b.db); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			b.log.Error().Str("target", target.ID).Msg("target not found")
			return nil, &ssh.BannerError{
				Message: "target not found\n",
			}
		}

		b.log.Error().Str("target", target.ID).Err(err).Msg("load target from DB")
		return nil, &ssh.BannerError{
			Message: "internal server error\n",
		}
	}

	if !target.SSH.Enabled {
		b.log.Error().Str("target", target.ID).Msg("ssh transport disabled for target")

		return nil, &ssh.BannerError{
			Message: "SSH is not enabled for this target\n",
		}
	}

	// Authenticate the user with their SSH key against the authorized ones
	found := false
	for _, a := range target.SSH.AuthorizedKeys {
		aKey, _, _, _, err := ssh.ParseAuthorizedKey([]byte(a))
		if err != nil {
			b.log.Error().Str("target", target.ID).Str("authorized_key", a).Err(err).Msg("parse SSH authorized key")
			continue
		}

		if bytes.Equal(ssh.MarshalAuthorizedKey(key), ssh.MarshalAuthorizedKey(aKey)) {
			found = true
			break
		}
	}

	if !found {
		b.log.Error().Str("target", target.ID).Msg("key authentication failed, no matching keys")

		return nil, &ssh.BannerError{
			Message: "key authentication failed. Ensure you've added your authorized_key to IsardVDI\n",
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
			Message: "internal server error\n",
		}
	}

	// Ensure the desktop is in a valid state
	if dktp.Status != "Started" {
		b.log.Error().Str("desktop", dktp.ID).Msg("desktop is not started")
		return nil, &ssh.BannerError{
			Message: "desktop is not started\n",
		}
	}

	if dktp.Viewer == nil {
		b.log.Error().Str("desktop", dktp.ID).Msg("desktop has no viewer")
		return nil, &ssh.BannerError{
			Message: "desktop has no viewer. Ensure it has the WireGuard interface\n",
		}
	}

	// Get the desktop IP
	if dktp.Viewer.GuestIP == nil {
		b.log.Error().Str("desktop", dktp.ID).Msg("desktop has no ip")
		return nil, &ssh.BannerError{
			Message: "desktop has no ip. Ensure it has the WireGuard interface\n",
		}
	}

	return &ssh.Permissions{
		Extensions: map[string]string{
			ExtensionRemoteUsr:        dktp.GuestProperties.Credentials.Username,
			ExtensionRemotePwd:        dktp.GuestProperties.Credentials.Password,
			ExtensionRemoteTargetHost: *dktp.Viewer.GuestIP,
			ExtensionRemoteTargetPort: strconv.Itoa(target.SSH.Port),
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
		log.Error().Err(err).Msg("create ssh connection")
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
		// TODO: Send a better looking error
		log.Error().Err(err).Msg("establish SSH proxy client connection")
		return
	}
	defer targetConn.Close()

	log.Debug().Msg("created SSH connection. Starting to proxy")

	// Start proxying
	go b.handleRequests(ctx, log, targetConn, reqs)
	b.handleChannels(ctx, log, targetConn, chans)
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
