package main

import (
	"context"
	"os"
	"os/signal"

	certwatch "gitlab.com/isard/isardvdi/haproxy-sync/cert-watch"
	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/pkg/log"
	pkgTls "gitlab.com/isard/isardvdi/pkg/tls"
)

func main() {
	cfg := cfg.New()

	log := log.New("cert-watch", cfg.Log.Level)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	haproxy := haproxy.NewHAProxy(log, cfg.HAProxy.SocketAddress)
	if err := haproxy.WaitReady(ctx, cfg.HAProxy.StartupTimeout); err != nil {
		log.Fatal().Err(err).Msg("wait for the HAProxy admin socket to become ready")
	}

	certWatch := certwatch.NewCertWatch(log, haproxy, cfg.HAProxy.Domains.CrtListPath)

	watcher := pkgTls.NewChangeWatcher(log, cfg.CertWatch.Interval, certWatch.Certs, certWatch.Update)

	log.Info().Msg("service started")

	watcher.Start(ctx)

	log.Info().Msg("stopping service")
}
