package http

import (
	"context"
	"net/http"
	"sync"
	"time"

	"github.com/bolkedebruin/rdpgw/common"
	"github.com/bolkedebruin/rdpgw/protocol"
	"github.com/rs/zerolog"
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

	s := http.Server{
		Addr:    r.Addr,
		Handler: m,
	}

	go func() {
		if err := s.ListenAndServeTLS("/portal-certs/chain.pem", "/portal-certs/chain.pem"); err != nil {
			r.Log.Fatal().Err(err).Str("addr", r.Addr).Msg("serve http")
		}
	}()

	<-ctx.Done()

	timeout, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	s.Shutdown(timeout)
	r.WG.Done()
}
