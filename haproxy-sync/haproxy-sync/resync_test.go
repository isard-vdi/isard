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
	"github.com/stretchr/testify/require"
)

type answer func(haproxysync.ResyncRequest) (syncErr string, reply bool)

func succeed(haproxysync.ResyncRequest) (string, bool) { return "", true }

func newResyncSvc(t *testing.T, m *haproxy.MockHaproxy) *haproxysync.HAproxySync {
	t.Helper()

	svc := haproxysync.Init(log.New("test", "debug"), cfg.HAProxy{}, m, nil)
	svc.SetResyncTimings(time.Second, time.Millisecond, 4*time.Millisecond)

	return svc
}

// apiv4 opens a resync stream like apiv4 does, answers every request with answer and returns
// the requests in the order they arrived.
func apiv4(t *testing.T, svc *haproxysync.HAproxySync, answer answer) (<-chan haproxysync.ResyncRequest, context.CancelFunc) {
	t.Helper()

	ctx, cancel := context.WithCancel(t.Context())
	reqs := make(chan haproxysync.ResyncRequest, 64)
	done := make(chan struct{})

	go func() {
		defer close(done)
		_ = svc.WatchResync(ctx, func(r haproxysync.ResyncRequest) error {
			reqs <- r
			if syncErr, reply := answer(r); reply {
				svc.AckResync(r.ID, syncErr)
			}
			return nil
		})
	}()

	stop := func() {
		cancel()
		<-done
	}
	t.Cleanup(stop)

	return reqs, stop
}

func next(t *testing.T, reqs <-chan haproxysync.ResyncRequest) haproxysync.ResyncRequest {
	t.Helper()

	select {
	case r := <-reqs:
		return r
	case <-time.After(5 * time.Second):
		t.Fatal("no resync request")
		return haproxysync.ResyncRequest{}
	}
}

func quiet(t *testing.T, reqs <-chan haproxysync.ResyncRequest) {
	t.Helper()

	select {
	case r := <-reqs:
		t.Fatalf("unexpected resync request %+v", r)
	case <-time.After(100 * time.Millisecond):
	}
}

func TestWatchResyncAsksForAResyncOnConnect(t *testing.T) {
	assert := assert.New(t)

	svc := newResyncSvc(t, haproxy.NewMockHaproxy(t))

	first, closeFirst := apiv4(t, svc, succeed)
	assert.Equal(haproxysync.ResyncReasonStarted, next(t, first).Reason)
	closeFirst()

	second, _ := apiv4(t, svc, succeed)
	assert.Equal(haproxysync.ResyncReasonReopened, next(t, second).Reason)
	quiet(t, second)
}

func TestNotifyReloadWaitsForTheNewWorker(t *testing.T) {
	assert := assert.New(t)

	m := haproxy.NewMockHaproxy(t)
	m.On("ShowPid").Return(100, nil).Once()
	svc := newResyncSvc(t, m)
	svc.RecordWorkerPid()

	reqs, _ := apiv4(t, svc, succeed)
	next(t, reqs)

	// the old worker still answers twice before the new one takes the socket
	m.On("ShowPid").Return(100, nil).Twice()
	m.On("ShowPid").Return(101, nil).Once()
	svc.NotifyReload(t.Context())

	assert.Equal(haproxysync.ResyncReasonReload, next(t, reqs).Reason)
	m.AssertNumberOfCalls(t, "ShowPid", 4)
}

func TestEveryWatcherGetsTheReload(t *testing.T) {
	assert := assert.New(t)

	m := haproxy.NewMockHaproxy(t)
	m.On("ShowPid").Return(7, nil)
	svc := newResyncSvc(t, m)

	a, _ := apiv4(t, svc, succeed)
	assert.Equal(haproxysync.ResyncReasonStarted, next(t, a).Reason)
	b, _ := apiv4(t, svc, succeed)
	assert.Equal(haproxysync.ResyncReasonReopened, next(t, b).Reason)
	assert.Equal(haproxysync.ResyncReasonReopened, next(t, a).Reason)

	svc.NotifyReload(t.Context())

	assert.Equal(haproxysync.ResyncReasonReload, next(t, a).Reason)
	assert.Equal(haproxysync.ResyncReasonReload, next(t, b).Reason)
}

func TestAFailedResyncIsRetriedUntilItSucceeds(t *testing.T) {
	assert := assert.New(t)

	svc := newResyncSvc(t, haproxy.NewMockHaproxy(t))

	failures := 3
	reqs, _ := apiv4(t, svc, func(haproxysync.ResyncRequest) (string, bool) {
		if failures > 0 {
			failures--
			return "rethinkdb down", true
		}
		return "", true
	})

	var last uint64
	for range 4 {
		r := next(t, reqs)
		assert.Equal(haproxysync.ResyncReasonStarted, r.Reason)
		assert.Greater(r.ID, last)
		last = r.ID
	}
	quiet(t, reqs)
}

func TestAnUnansweredResyncIsRetried(t *testing.T) {
	svc := newResyncSvc(t, haproxy.NewMockHaproxy(t))
	svc.SetResyncTimings(20*time.Millisecond, time.Millisecond, 4*time.Millisecond)

	answered := false
	reqs, _ := apiv4(t, svc, func(haproxysync.ResyncRequest) (string, bool) {
		if !answered {
			answered = true
			return "", false
		}
		return "", true
	})

	first, second := next(t, reqs), next(t, reqs)
	assert.Greater(t, second.ID, first.ID)
	quiet(t, reqs)
}

func TestAReloadReplacesTheResyncBeingRetried(t *testing.T) {
	require := require.New(t)

	m := haproxy.NewMockHaproxy(t)
	m.On("ShowPid").Return(7, nil)
	svc := newResyncSvc(t, m)

	var lastStarted uint64
	reloads := 0
	reqs, _ := apiv4(t, svc, func(r haproxysync.ResyncRequest) (string, bool) {
		if r.Reason != haproxysync.ResyncReasonReload {
			lastStarted = r.ID
			return "rethinkdb down", true
		}

		reloads++
		if reloads == 1 {
			// a late success for the superseded request must not end the new cycle
			svc.AckResync(lastStarted, "")
			return "rethinkdb down", true
		}
		return "", true
	})

	require.Equal(haproxysync.ResyncReasonStarted, next(t, reqs).Reason)
	require.Equal(haproxysync.ResyncReasonStarted, next(t, reqs).Reason)

	svc.NotifyReload(t.Context())

	r := next(t, reqs)
	for r.Reason == haproxysync.ResyncReasonStarted {
		r = next(t, reqs)
	}
	require.Equal(haproxysync.ResyncReasonReload, r.Reason)
	require.Equal(haproxysync.ResyncReasonReload, next(t, reqs).Reason)
	quiet(t, reqs)
}

func TestAReconnectedWatcherGetsTheResyncThatFailed(t *testing.T) {
	svc := newResyncSvc(t, haproxy.NewMockHaproxy(t))

	failing, closeFailing := apiv4(t, svc, func(haproxysync.ResyncRequest) (string, bool) {
		return "connection reset", true
	})
	next(t, failing)
	closeFailing()

	reqs, _ := apiv4(t, svc, succeed)
	assert.Equal(t, haproxysync.ResyncReasonReopened, next(t, reqs).Reason)
	quiet(t, reqs)
}
