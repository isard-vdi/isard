package http

import (
	"context"
	"crypto/tls"
	"net/http"
	"sync"
	"time"

	tlsReloader "gitlab.com/isard/isardvdi/pkg/tls"

	"github.com/bolkedebruin/rdpgw/common"
	"github.com/bolkedebruin/rdpgw/protocol"
	"github.com/rs/zerolog"
)

const (
	certPath = "/portal-certs/chain.pem"
	keyPath  = "/portal-certs/chain.pem"
)

type RDPGwServer struct {
	Addr    string
	Gateway *protocol.Gateway

	Log *zerolog.Logger
	WG  *sync.WaitGroup
}

func (r *RDPGwServer) Serve(ctx context.Context) {
	m := http.NewServeMux()
	m.Handle("/remoteDesktopGateway/", common.EnrichContext(http.HandlerFunc(r.Gateway.HandleGatewayProtocol)))

	kpr, err := tlsReloader.NewKeyPairReloader(certPath, keyPath)
	if err != nil {
		r.Log.Fatal().Err(err).Msg("create tls certificate reloader")
	}

	tlsCfg := &tls.Config{
		GetCertificate: kpr.GetCertificate,
	}

	s := http.Server{
		Addr:      r.Addr,
		Handler:   m,
		TLSConfig: tlsCfg,
	}

	go func() {
		if err := kpr.Start(ctx, r.Log); err != nil {
			r.Log.Fatal().Err(err).Msg("start certificate reloader")
		}
	}()

	go func() {
		if err := s.ListenAndServeTLS("", ""); err != nil {
			r.Log.Fatal().Err(err).Str("addr", r.Addr).Msg("serve http")
		}
	}()

	<-ctx.Done()

	timeout, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	s.Shutdown(timeout)
	r.WG.Done()
}
