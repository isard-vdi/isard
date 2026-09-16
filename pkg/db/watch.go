package db

import (
	"context"
	"sync"
	"time"

	"github.com/google/go-cmp/cmp"
	"github.com/rs/zerolog"
)

// Change is a configuration transition. On the first emission, Old is the zero value of T.
type Change[T any] struct {
	Old T
	New T
}

// Watcher periodically loads a configuration value and reports the transitions.
type Watcher[T any] struct {
	log      *zerolog.Logger
	interval time.Duration
	load     func(context.Context) (T, error)

	mux     sync.RWMutex
	current T

	changes chan Change[T]
}

// NewWatcher creates a configuration watcher. If buffer is 0 the watcher does not
// emit changes and Changes returns nil; consumers that only need the latest value
// use Current instead.
func NewWatcher[T any](log *zerolog.Logger, interval time.Duration, buffer int, load func(context.Context) (T, error)) *Watcher[T] {
	w := &Watcher[T]{
		log:      log,
		interval: interval,
		load:     load,
	}

	if buffer > 0 {
		w.changes = make(chan Change[T], buffer)
	}

	return w
}

// Changes returns the channel the transitions are emitted to, or nil if the
// watcher was created with a buffer of 0.
func (w *Watcher[T]) Changes() <-chan Change[T] {
	return w.changes
}

// Current returns the last successfully loaded value. It is safe to call from
// multiple goroutines, and it is only meaningful once Start has returned nil.
func (w *Watcher[T]) Current() T {
	w.mux.RLock()
	defer w.mux.RUnlock()

	return w.current
}

// Start loads the configuration for the first time and then keeps it up to date
// until ctx is cancelled. It returns an error if the first load fails. When it
// returns nil and the watcher has a change channel, the initial change has
// already been emitted, even if ctx was cancelled before the call.
func (w *Watcher[T]) Start(ctx context.Context, wg *sync.WaitGroup) error {
	current, err := w.load(ctx)
	if err != nil {
		return err
	}

	w.mux.Lock()
	w.current = current
	w.mux.Unlock()

	if w.changes != nil {
		w.changes <- Change[T]{New: current}
	}

	wg.Go(func() {
		ticker := time.NewTicker(w.interval)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return

			case <-ticker.C:
			}

			next, err := w.load(ctx)
			if err != nil {
				w.log.Error().Err(err).Msg("reload configuration")

				continue
			}

			current := w.Current()
			if cmp.Equal(current, next) {
				continue
			}

			w.mux.Lock()
			w.current = next
			w.mux.Unlock()

			if w.changes == nil {
				continue
			}

			select {
			case <-ctx.Done():
				return

			case w.changes <- Change[T]{Old: current, New: next}:
			}
		}
	})

	return nil
}
