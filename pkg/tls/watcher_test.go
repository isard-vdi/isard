package tls_test

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"slices"
	"sync/atomic"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/pkg/log"
	pkgTls "gitlab.com/isard/isardvdi/pkg/tls"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestChangeWatcherCheck(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareFiles  func(dir string) ([]string, error)
		PrepareChange func(t *testing.T, dir string)
		OnChangeErr   error
		ExpectedRan   bool
		ExpectedCalls [][]string
		ExpectedErr   string
	}{
		"should run the action if the contents change": {
			PrepareFiles: func(dir string) ([]string, error) {
				return []string{filepath.Join(dir, "chain.pem")}, nil
			},
			PrepareChange: func(t *testing.T, dir string) {
				require.NoError(t, os.WriteFile(filepath.Join(dir, "chain.pem"), []byte("new"), 0o644))
			},
			ExpectedRan:   true,
			ExpectedCalls: [][]string{{"chain.pem"}},
		},
		"should sort the changed paths if several files change at once": {
			PrepareFiles: func(dir string) ([]string, error) {
				return []string{
					filepath.Join(dir, "d.pem"),
					filepath.Join(dir, "c.pem"),
					filepath.Join(dir, "b.pem"),
					filepath.Join(dir, "a.pem"),
				}, nil
			},
			PrepareChange: func(t *testing.T, dir string) {
				for _, name := range []string{"a.pem", "b.pem", "c.pem", "d.pem"} {
					require.NoError(t, os.WriteFile(filepath.Join(dir, name), []byte("new"), 0o644))
				}
			},
			ExpectedRan:   true,
			ExpectedCalls: [][]string{{"a.pem", "b.pem", "c.pem", "d.pem"}},
		},
		"should hash a file referenced twice only once": {
			PrepareFiles: func(dir string) ([]string, error) {
				path := filepath.Join(dir, "chain.pem")

				return []string{path, path}, nil
			},
			PrepareChange: func(t *testing.T, dir string) {
				require.NoError(t, os.WriteFile(filepath.Join(dir, "chain.pem"), []byte("new"), 0o644))
			},
			ExpectedRan:   true,
			ExpectedCalls: [][]string{{"chain.pem"}},
		},
		"should skip a file that doesn't exist yet": {
			PrepareFiles: func(dir string) ([]string, error) {
				return []string{filepath.Join(dir, "missing.pem")}, nil
			},
		},
		"should not run the action if the contents don't change": {
			PrepareFiles: func(dir string) ([]string, error) {
				return []string{filepath.Join(dir, "chain.pem")}, nil
			},
		},
		"should return an error if the files can't be listed": {
			PrepareFiles: func(dir string) ([]string, error) {
				return nil, errors.New("crt-list is broken")
			},
			ExpectedErr: "list the files to watch: crt-list is broken",
		},
		"should return an error if a watched file can't be read": {
			PrepareFiles: func(dir string) ([]string, error) {
				return []string{"/"}, nil
			},
			ExpectedErr: "read the watched file '/': read /: is a directory",
		},
		"should keep the previous state if the action fails": {
			PrepareFiles: func(dir string) ([]string, error) {
				return []string{filepath.Join(dir, "chain.pem")}, nil
			},
			PrepareChange: func(t *testing.T, dir string) {
				require.NoError(t, os.WriteFile(filepath.Join(dir, "chain.pem"), []byte("new"), 0o644))
			},
			OnChangeErr:   errors.New("reload failed"),
			ExpectedCalls: [][]string{{"chain.pem"}},
			ExpectedErr:   "reload failed",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dir := t.TempDir()
			require.NoError(t, os.WriteFile(filepath.Join(dir, "chain.pem"), []byte("old"), 0o644))

			var expectedCalls [][]string
			for _, call := range tc.ExpectedCalls {
				changed := make([]string, 0, len(call))
				for _, file := range call {
					changed = append(changed, filepath.Join(dir, file))
				}

				expectedCalls = append(expectedCalls, changed)
			}

			var calls [][]string
			logger := log.New("test", "debug")

			files := func() ([]string, error) {
				return tc.PrepareFiles(dir)
			}

			onChange := func(changed []string) error {
				calls = append(calls, changed)

				return tc.OnChangeErr
			}

			w := pkgTls.NewChangeWatcher(logger, time.Minute, files, onChange)

			w.Seed()

			if tc.PrepareChange != nil {
				tc.PrepareChange(t, dir)
			}

			ran, err := w.Check()

			assert.Equal(tc.ExpectedRan, ran)
			assert.Equal(expectedCalls, calls)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)

				if tc.OnChangeErr != nil {
					// A failed action must leave the state untouched so the next tick
					// retries it.
					_, err := w.Check()
					assert.EqualError(err, tc.ExpectedErr)
					assert.Equal(slices.Concat(expectedCalls, expectedCalls), calls)
				}

				return
			}

			assert.NoError(err)
		})
	}
}

func TestChangeWatcherStart(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareChange        func(t *testing.T, path string, broken *atomic.Bool)
		ExpectedChanged      []string
		ExpectedKeepsPolling bool
	}{
		"should not run the action for the contents already on disk": {},
		"should run the action if a watched file changes": {
			PrepareChange: func(t *testing.T, path string, broken *atomic.Bool) {
				require.NoError(t, os.WriteFile(path, []byte("new"), 0o644))
			},
			ExpectedChanged: []string{"chain.pem"},
		},
		"should keep polling if a check fails": {
			PrepareChange: func(t *testing.T, path string, broken *atomic.Bool) {
				broken.Store(true)
			},
			ExpectedKeepsPolling: true,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dir := t.TempDir()
			path := filepath.Join(dir, "chain.pem")
			require.NoError(t, os.WriteFile(path, []byte("old"), 0o644))

			var expectedChanged []string
			for _, file := range tc.ExpectedChanged {
				expectedChanged = append(expectedChanged, filepath.Join(dir, file))
			}

			changed := make(chan []string, 4)
			listed := make(chan struct{}, 2)
			logger := log.New("test", "debug")

			var broken atomic.Bool

			files := func() ([]string, error) {
				if broken.Load() {
					select {
					case listed <- struct{}{}:
					default:
					}

					return nil, errors.New("crt-list is broken")
				}

				return []string{path}, nil
			}

			onChange := func(c []string) error {
				changed <- c

				return nil
			}

			w := pkgTls.NewChangeWatcher(logger, 10*time.Millisecond, files, onChange)

			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()

			go w.Start(ctx)

			// The seeding pass must not fire the action for the contents already on
			// disk, so let a few ticks go by before changing anything.
			select {
			case c := <-changed:
				t.Fatalf("the action ran on the initial state: %v", c)

			case <-time.After(50 * time.Millisecond):
			}

			if tc.PrepareChange != nil {
				tc.PrepareChange(t, path, &broken)
			}

			if expectedChanged != nil {
				select {
				case c := <-changed:
					assert.Equal(expectedChanged, c)

				case <-time.After(2 * time.Second):
					t.Fatal("the action never ran after the file changed")
				}
			}

			if !tc.ExpectedKeepsPolling {
				return
			}

			// A failed check must not stop the loop, so the next ticks keep polling.
			for range 2 {
				select {
				case <-listed:

				case <-time.After(2 * time.Second):
					t.Fatal("the poll stopped after a failed check")
				}
			}
		})
	}
}
