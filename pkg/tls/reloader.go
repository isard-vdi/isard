package tls

// Copied between https://github.com/kubernetes-sigs/controller-runtime/blob/master/pkg/certwatcher/certwatcher.go and https://stackoverflow.com/a/40883377

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"
	"github.com/rs/zerolog"
)

// pollInterval is how often the certificate files are checked for changes. fsnotify
// doesn't fire for a certificate renewed on the server side of a network filesystem,
// so the poll is the mechanism that actually catches a centrally renewed certificate.
const pollInterval = 60 * time.Second

type keypairReloader struct {
	log *zerolog.Logger

	mux     sync.RWMutex
	watcher *fsnotify.Watcher
	poll    *ChangeWatcher

	cert *tls.Certificate

	certPath string
	keyPath  string
}

func NewKeyPairReloader(log *zerolog.Logger, certPath, keyPath string) (*keypairReloader, error) {
	kpr := &keypairReloader{
		log:      log,
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

	files := func() ([]string, error) {
		return []string{kpr.certPath, kpr.keyPath}, nil
	}

	onChange := func([]string) error {
		if err := kpr.ReadCertificate(); err != nil {
			return err
		}

		log.Info().Msg("tls certificate reloaded")

		return nil
	}

	kpr.poll = NewChangeWatcher(log, pollInterval, files, onChange)

	return kpr, nil
}

func (kpr *keypairReloader) Start(ctx context.Context) error {
	files := []string{kpr.certPath, kpr.keyPath}
	for _, f := range files {
		if err := kpr.watcher.Add(f); err != nil {
			err = fmt.Errorf("add '%s' to the filesystem watcher: %w", f, err)

			if closeErr := kpr.watcher.Close(); closeErr != nil {
				return fmt.Errorf("%w (also failed to close the filesystem watcher: %w)", err, closeErr)
			}

			return err
		}
	}

	go kpr.poll.Start(ctx)

	go func() {
		for {
			select {
			case event, ok := <-kpr.watcher.Events:
				if !ok {
					return
				}

				if event.Has(fsnotify.Remove) {
					if err := kpr.watcher.Add(event.Name); err != nil {
						kpr.log.Error().Err(err).Msg("rewatch certificate changes")
					}

				} else if !event.Has(fsnotify.Create) && !event.Has(fsnotify.Write) {
					continue
				}

				// The filesystem event is only a hint to check early: the watcher
				// hashes the contents, so an event that doesn't change the
				// certificate is a no-op and the poll never reloads it twice.
				if _, err := kpr.poll.Check(); err != nil {
					kpr.log.Error().Err(err).Msg("reload certificate")
				}

			case err, ok := <-kpr.watcher.Errors:
				if !ok {
					return
				}

				kpr.log.Error().Err(err).Msg("certificate filesystem watch error")
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

	// LoadX509KeyPair doesn't populate Leaf, and serving it saves the handshake a parse.
	if len(cert.Certificate) > 0 {
		leaf, err := x509.ParseCertificate(cert.Certificate[0])
		if err != nil {
			return fmt.Errorf("parse tls certificate: %w", err)
		}

		cert.Leaf = leaf
	}

	kpr.cert = &cert

	return nil
}

func (kpr *keypairReloader) GetCertificate(*tls.ClientHelloInfo) (*tls.Certificate, error) {
	kpr.mux.RLock()
	defer kpr.mux.RUnlock()

	return kpr.cert, nil
}
