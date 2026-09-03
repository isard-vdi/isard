package tls

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"slices"
	"sync"
	"time"

	"github.com/rs/zerolog"
)

// ChangeWatcher polls a set of files and runs an action when their contents change.
// inotify only reports events triggered through the local filesystem API, so it never
// fires for a file renewed on the server side of a network filesystem (see inotify(7),
// which states that applications must fall back to polling to catch such events).
type ChangeWatcher struct {
	log      *zerolog.Logger
	interval time.Duration
	files    func() ([]string, error)
	onChange func(changed []string) error

	mux    sync.Mutex
	hashes map[string]string
}

// NewChangeWatcher returns a watcher that runs onChange with the paths whose contents
// changed since the last successful check.
func NewChangeWatcher(log *zerolog.Logger, interval time.Duration, files func() ([]string, error), onChange func(changed []string) error) *ChangeWatcher {
	return &ChangeWatcher{
		log:      log,
		interval: interval,
		files:    files,
		onChange: onChange,
		hashes:   map[string]string{},
	}
}

// Seed records the current contents of the watched files without running the action.
func (w *ChangeWatcher) Seed() {
	w.mux.Lock()
	defer w.mux.Unlock()

	hashes, err := w.hash()
	if err != nil {
		w.log.Error().Err(err).Msg("read the initial contents of the watched files")

		return
	}

	w.hashes = hashes
}

// Check runs a single poll iteration. It reports whether the action was run.
func (w *ChangeWatcher) Check() (bool, error) {
	w.mux.Lock()
	defer w.mux.Unlock()

	hashes, err := w.hash()
	if err != nil {
		return false, err
	}

	changed := []string{}
	for path, hash := range hashes {
		if w.hashes[path] != hash {
			changed = append(changed, path)
		}
	}

	if len(changed) == 0 {
		w.hashes = hashes

		return false, nil
	}

	slices.Sort(changed)

	// The state is only advanced on success, so a failed action is retried on the
	// next tick instead of being silently swallowed.
	if err := w.onChange(changed); err != nil {
		return false, err
	}

	w.hashes = hashes

	return true, nil
}

// Start seeds the state and then polls until the context is done.
func (w *ChangeWatcher) Start(ctx context.Context) {
	w.Seed()

	ticker := time.NewTicker(w.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return

		case <-ticker.C:
			if _, err := w.Check(); err != nil {
				w.log.Error().Err(err).Msg("check the watched files for changes")
			}
		}
	}
}

// hash returns the sha256 of the contents of each watched file, skipping the ones that
// don't exist yet. The caller must hold the mutex.
func (w *ChangeWatcher) hash() (map[string]string, error) {
	files, err := w.files()
	if err != nil {
		return nil, fmt.Errorf("list the files to watch: %w", err)
	}

	hashes := map[string]string{}
	for _, path := range files {
		if _, ok := hashes[path]; ok {
			continue
		}

		b, err := os.ReadFile(path)
		if err != nil {
			if errors.Is(err, fs.ErrNotExist) {
				w.log.Debug().Str("path", path).Msg("watched file doesn't exist yet")

				continue
			}

			return nil, fmt.Errorf("read the watched file '%s': %w", path, err)
		}

		sum := sha256.Sum256(b)
		hashes[path] = hex.EncodeToString(sum[:])
	}

	return hashes, nil
}
