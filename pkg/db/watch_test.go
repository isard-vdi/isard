package db_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	"gitlab.com/isard/isardvdi/pkg/db"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type watchCfg struct {
	Enabled bool
	Name    string
}

func drainChanges[T any](ch <-chan db.Change[T]) []db.Change[T] {
	var changes []db.Change[T]

	for {
		select {
		case change := <-ch:
			changes = append(changes, change)

		default:
			return changes
		}
	}
}

func TestWatcherStart(t *testing.T) {
	t.Parallel()

	interval := 10 * time.Millisecond

	cases := map[string]struct {
		Buffer            int
		Load              func(call int) (watchCfg, error)
		Ticks             int
		CancelBeforeStart bool
		NoDrain           bool
		ExpectedStartErr  string
		ExpectedCurrent   watchCfg
		ExpectedChanges   []db.Change[watchCfg]
	}{
		"should load the configuration and emit the initial change": {
			Buffer: 1024,
			Load: func(int) (watchCfg, error) {
				return watchCfg{Enabled: true, Name: "first"}, nil
			},
			Ticks:           0,
			ExpectedCurrent: watchCfg{Enabled: true, Name: "first"},
			ExpectedChanges: []db.Change[watchCfg]{{
				New: watchCfg{Enabled: true, Name: "first"},
			}},
		},
		"should not emit anything if the configuration does not change": {
			Buffer: 1024,
			Load: func(int) (watchCfg, error) {
				return watchCfg{Enabled: true, Name: "first"}, nil
			},
			Ticks:           3,
			ExpectedCurrent: watchCfg{Enabled: true, Name: "first"},
			ExpectedChanges: []db.Change[watchCfg]{{
				New: watchCfg{Enabled: true, Name: "first"},
			}},
		},
		"should emit a change and update the current value if the configuration changes": {
			Buffer: 1024,
			Load: func(call int) (watchCfg, error) {
				if call == 0 {
					return watchCfg{Enabled: true, Name: "first"}, nil
				}

				return watchCfg{Enabled: false, Name: "second"}, nil
			},
			Ticks:           1,
			ExpectedCurrent: watchCfg{Enabled: false, Name: "second"},
			ExpectedChanges: []db.Change[watchCfg]{{
				New: watchCfg{Enabled: true, Name: "first"},
			}, {
				Old: watchCfg{Enabled: true, Name: "first"},
				New: watchCfg{Enabled: false, Name: "second"},
			}},
		},
		"should keep the last known value if a reload fails": {
			Buffer: 1024,
			Load: func(call int) (watchCfg, error) {
				if call == 0 {
					return watchCfg{Enabled: true, Name: "first"}, nil
				}

				return watchCfg{}, errors.New("connection refused")
			},
			Ticks:           2,
			ExpectedCurrent: watchCfg{Enabled: true, Name: "first"},
			ExpectedChanges: []db.Change[watchCfg]{{
				New: watchCfg{Enabled: true, Name: "first"},
			}},
		},
		"should return an error if the initial load fails": {
			Buffer: 1024,
			Load: func(int) (watchCfg, error) {
				return watchCfg{}, errors.New("connection refused")
			},
			ExpectedStartErr: "connection refused",
		},
		"should not emit changes if the buffer is zero": {
			Buffer: 0,
			Load: func(call int) (watchCfg, error) {
				if call == 0 {
					return watchCfg{Enabled: true, Name: "first"}, nil
				}

				return watchCfg{Enabled: false, Name: "second"}, nil
			},
			Ticks:           1,
			ExpectedCurrent: watchCfg{Enabled: false, Name: "second"},
		},
		"should stop sending a change if the context is cancelled while the buffer is full": {
			Buffer: 1,
			Load: func(call int) (watchCfg, error) {
				if call == 0 {
					return watchCfg{Enabled: true, Name: "first"}, nil
				}

				return watchCfg{Enabled: false, Name: "second"}, nil
			},
			Ticks:           1,
			NoDrain:         true,
			ExpectedCurrent: watchCfg{Enabled: false, Name: "second"},
		},
		"should emit the initial change even if the context is already cancelled": {
			Buffer: 1024,
			Load: func(int) (watchCfg, error) {
				return watchCfg{Enabled: true, Name: "first"}, nil
			},
			CancelBeforeStart: true,
			ExpectedCurrent:   watchCfg{Enabled: true, Name: "first"},
			ExpectedChanges: []db.Change[watchCfg]{{
				New: watchCfg{Enabled: true, Name: "first"},
			}},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			synctest.Test(t, func(t *testing.T) {
				assert := assert.New(t)
				require := require.New(t)

				ctx, cancel := context.WithCancel(t.Context())
				defer cancel()

				logger := log.New("test", "debug")

				calls := 0
				load := func(context.Context) (watchCfg, error) {
					cfg, err := tc.Load(calls)
					calls += 1

					return cfg, err
				}

				watcher := db.NewWatcher(logger, interval, tc.Buffer, load)

				var wg sync.WaitGroup

				if tc.CancelBeforeStart {
					cancel()
				}

				err := watcher.Start(ctx, &wg)

				if tc.ExpectedStartErr != "" {
					assert.EqualError(err, tc.ExpectedStartErr)
					assert.Equal(watchCfg{}, watcher.Current())

					cancel()
					synctest.Wait()
					wg.Wait()

					return
				}

				require.NoError(err)

				if tc.Buffer == 0 {
					assert.Nil(watcher.Changes())
				}

				for range tc.Ticks {
					time.Sleep(interval)
					synctest.Wait()
				}

				assert.Equal(tc.ExpectedCurrent, watcher.Current())

				if !tc.NoDrain {
					assert.Equal(tc.ExpectedChanges, drainChanges(watcher.Changes()))
				}

				cancel()
				synctest.Wait()
				wg.Wait()
			})
		})
	}
}
