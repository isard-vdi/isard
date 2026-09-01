package providermanager

import (
	"context"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/authentication/provider"

	"github.com/rs/zerolog"
)

const providerLoadRetryInterval = 30 * time.Second

type providerLoader[T any] struct {
	prv     provider.ConfigurableProvider[T]
	changes <-chan T

	mux    sync.RWMutex
	prvCfg *T
	prvErr error
}

func newProviderLoader[T any](prv provider.ConfigurableProvider[T], changes <-chan T) *providerLoader[T] {
	return &providerLoader[T]{
		prv:     prv,
		changes: changes,
	}
}

func (l *providerLoader[T]) Watch(ctx context.Context, log *zerolog.Logger) {
	retry := time.NewTicker(providerLoadRetryInterval)
	defer retry.Stop()

	for {
		select {
		case <-ctx.Done():
			return

		case cfg := <-l.changes:
			l.load(ctx, log, cfg)

		case <-retry.C:
			l.mux.RLock()
			cfg, err := l.prvCfg, l.prvErr
			l.mux.RUnlock()

			if cfg == nil || err == nil {
				continue
			}

			log.Debug().Str("provider", l.prv.String()).Msg("retrying the provider configuration load")
			l.load(ctx, log, *cfg)
		}
	}
}

func (l *providerLoader[T]) load(ctx context.Context, log *zerolog.Logger, cfg T) {
	log.Debug().Str("provider", l.prv.String()).Msg("reloading provider configuration")

	err := l.prv.LoadConfig(ctx, cfg)

	l.mux.Lock()
	defer l.mux.Unlock()

	l.prvCfg = &cfg
	l.prvErr = err

	if err != nil {
		log.Error().Err(err).Str("provider", l.prv.String()).Msg("load new provider configuration")
		return
	}

	log.Info().Str("provider", l.prv.String()).Msg("successfully reloaded provider configuration")
}
