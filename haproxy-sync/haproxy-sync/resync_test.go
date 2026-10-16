package haproxysync_test

import (
	"context"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
)

// watch opens a resync stream and returns the channel its reasons arrive on.
func watch(t *testing.T, svc *haproxysync.HAproxySync) (<-chan string, context.CancelFunc) {
	t.Helper()

	ctx, cancel := context.WithCancel(t.Context())
	reasons := make(chan string, 8)
	done := make(chan struct{})

	go func() {
		defer close(done)
		_ = svc.WatchResync(ctx, func(reason string) error {
			reasons <- reason
			return nil
		})
	}()

	t.Cleanup(func() {
		cancel()
		<-done
	})

	return reasons, cancel
}

func next(t *testing.T, reasons <-chan string) string {
	t.Helper()

	select {
	case r := <-reasons:
		return r
	case <-time.After(5 * time.Second):
		t.Fatal("no resync request")
		return ""
	}
}

func TestWatchResyncAsksForAResyncOnConnect(t *testing.T) {
	assert := assert.New(t)

	svc := haproxysync.Init(log.New("test", "debug"), cfg.HAProxy{}, haproxy.NewMockHaproxy(t), nil)

	first, closeFirst := watch(t, svc)
	assert.Equal(haproxysync.ResyncReasonStarted, next(t, first))
	closeFirst()

	second, _ := watch(t, svc)
	assert.Equal(haproxysync.ResyncReasonReopened, next(t, second))
}

func TestNotifyReloadWaitsForTheNewWorker(t *testing.T) {
	assert := assert.New(t)

	m := haproxy.NewMockHaproxy(t)
	m.On("ShowPid").Return(100, nil).Once()
	svc := haproxysync.Init(log.New("test", "debug"), cfg.HAProxy{}, m, nil)
	svc.RecordWorkerPid()

	reasons, _ := watch(t, svc)
	next(t, reasons)

	// the old worker still answers twice before the new one takes the socket
	m.On("ShowPid").Return(100, nil).Twice()
	m.On("ShowPid").Return(101, nil).Once()
	svc.NotifyReload(t.Context())

	assert.Equal(haproxysync.ResyncReasonReload, next(t, reasons))
	m.AssertNumberOfCalls(t, "ShowPid", 4)
}

func TestEveryWatcherGetsTheReload(t *testing.T) {
	assert := assert.New(t)

	m := haproxy.NewMockHaproxy(t)
	m.On("ShowPid").Return(7, nil)
	svc := haproxysync.Init(log.New("test", "debug"), cfg.HAProxy{}, m, nil)

	a, _ := watch(t, svc)
	b, _ := watch(t, svc)
	next(t, a)
	next(t, b)

	svc.NotifyReload(t.Context())

	assert.Equal(haproxysync.ResyncReasonReload, next(t, a))
	assert.Equal(haproxysync.ResyncReasonReload, next(t, b))
}
