package tls

// Copied between https://github.com/kubernetes-sigs/controller-runtime/blob/master/pkg/certwatcher/certwatcher.go and https://stackoverflow.com/a/40883377

import (
	"context"
	"crypto/tls"
	"fmt"
	"sync"

	"github.com/fsnotify/fsnotify"
	"github.com/rs/zerolog"
)

type keypairReloader struct {
	mux     sync.RWMutex
	watcher *fsnotify.Watcher

	cert *tls.Certificate

	certPath string
	keyPath  string
}

func NewKeyPairReloader(certPath, keyPath string) (*keypairReloader, error) {
	kpr := &keypairReloader{
		certPath: certPath,
		keyPath:  keyPath,
	}

	if err := kpr.ReadCertificate(); err != nil {
		return nil, err
	}

	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, fmt.Errorf("create certificate filesystem watcher: %w", err)
	}

	kpr.watcher = watcher

	return kpr, nil
}

func (kpr *keypairReloader) Start(ctx context.Context, log *zerolog.Logger) error {
	files := []string{kpr.certPath, kpr.keyPath}
	for _, f := range files {
		if err := kpr.watcher.Add(f); err != nil {
			return fmt.Errorf("add '%s' to the filesystem watcher: %w", f, err)
		}
	}

	go func() {
		for {
			select {
			case event, ok := <-kpr.watcher.Events:
				if !ok {
					return
				}

				if event.Has(fsnotify.Remove) {
					if err := kpr.watcher.Add(event.Name); err != nil {
						log.Error().Err(err).Msg("rewatch certificate changes")
					}

				} else if !event.Has(fsnotify.Create) && !event.Has(fsnotify.Write) {
					continue
				}

				if err := kpr.ReadCertificate(); err != nil {
					log.Error().Err(err).Msg("reload certificate")
				}

				log.Info().Msg("tls certificate reloaded")

			case err, ok := <-kpr.watcher.Errors:
				if !ok {
					return
				}

				log.Error().Err(err).Msg("certificate filesystem watch error")
			}
		}
	}()

	<-ctx.Done()

	return kpr.watcher.Close()
}

func (kpr *keypairReloader) ReadCertificate() error {
	kpr.mux.Lock()
	defer kpr.mux.Unlock()

	cert, err := tls.LoadX509KeyPair(kpr.certPath, kpr.keyPath)
	if err != nil {
		return fmt.Errorf("read tls certificate: %w", err)
	}
	kpr.cert = &cert

	return nil
}

func (kpr *keypairReloader) GetCertificate(*tls.ClientHelloInfo) (*tls.Certificate, error) {
	kpr.mux.RLock()
	defer kpr.mux.RUnlock()

	return kpr.cert, nil
}
