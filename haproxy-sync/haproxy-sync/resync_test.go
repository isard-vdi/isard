package haproxysync_test

import (
	"context"
	"sync"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// workers answers ShowPid with the scripted pids in order, then keeps the last one.
type workers struct {
	*haproxy.MockHaproxy

	mux  sync.Mutex
	pids []int
}

func newWorkers(t *testing.T, pids ...int) *workers {
	return &workers{MockHaproxy: haproxy.NewMockHaproxy(t), pids: pids}
}

func (w *workers) ShowPid() (int, error) {
	w.mux.Lock()
	defer w.mux.Unlock()

	pid := w.pids[0]
	if len(w.pids) > 1 {
		w.pids = w.pids[1:]
	}

	return pid, nil
}

// set scripts the next pids ShowPid answers.
func (w *workers) set(pids ...int) {
	w.mux.Lock()
	defer w.mux.Unlock()

	w.pids = pids
}

type answer func(haproxysync.ResyncRequest) (syncErr string, reply bool)

func succeed(haproxysync.ResyncRequest) (string, bool) { return "", true }

func newResyncSvc(t *testing.T, w *workers) *haproxysync.HAproxySync {
	t.Helper()

	svc := haproxysync.Init(log.New("test", "debug"), cfg.HAProxy{Domains: cfg.HAProxyDomains{ACMEPath: "/etc/acme"}}, w, nil)
	svc.SetResyncTimings(time.Minute, time.Millisecond, 4*time.Millisecond)

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

// idle waits until the running resync cycle, if any, has ended.
func idle(t *testing.T, svc *haproxysync.HAproxySync) {
	t.Helper()

	require.Eventually(t, svc.ResyncIdle, 5*time.Second, time.Millisecond, "the resync cycle never ended")
}

// quiet checks that the resync cycle ended without sending anything more.
func quiet(t *testing.T, svc *haproxysync.HAproxySync, reqs <-chan haproxysync.ResyncRequest) {
	t.Helper()

	idle(t, svc)
	select {
	case r := <-reqs:
		t.Fatalf("unexpected resync request %+v", r)
	default:
	}
}

func TestWatchResyncAsksForAResyncOnConnect(t *testing.T) {
	assert := assert.New(t)

	svc := newResyncSvc(t, newWorkers(t, 7))

	first, closeFirst := apiv4(t, svc, succeed)
	assert.Equal(haproxysync.ResyncReasonStarted, next(t, first).Reason)
	idle(t, svc)
	closeFirst()

	second, _ := apiv4(t, svc, succeed)
	assert.Equal(haproxysync.ResyncReasonReopened, next(t, second).Reason)
	quiet(t, svc, second)
}

func TestNotifyReloadWaitsForTheNewWorker(t *testing.T) {
	assert := assert.New(t)

	w := newWorkers(t, 100)
	svc := newResyncSvc(t, w)
	svc.RecordWorkerPid()

	reqs, _ := apiv4(t, svc, succeed)
	next(t, reqs)
	idle(t, svc)

	// the old worker still answers twice before the new one takes the socket
	w.set(100, 100, 101)
	svc.NotifyReload(t.Context())

	assert.Equal(haproxysync.ResyncReasonReload, next(t, reqs).Reason)
	quiet(t, svc, reqs)
	assert.Equal(101, svc.WorkerPid())
}

func TestEveryWatcherGetsTheReload(t *testing.T) {
	assert := assert.New(t)

	w := newWorkers(t, 7)
	svc := newResyncSvc(t, w)
	svc.RecordWorkerPid()

	a, _ := apiv4(t, svc, succeed)
	assert.Equal(haproxysync.ResyncReasonStarted, next(t, a).Reason)
	b, _ := apiv4(t, svc, succeed)
	assert.Equal(haproxysync.ResyncReasonReopened, next(t, b).Reason)
	assert.Equal(haproxysync.ResyncReasonReopened, next(t, a).Reason)

	w.set(8)
	svc.NotifyReload(t.Context())

	assert.Equal(haproxysync.ResyncReasonReload, next(t, a).Reason)
	assert.Equal(haproxysync.ResyncReasonReload, next(t, b).Reason)
}

// A worker change between the request and the answer means the push reached the old worker.
func TestAResyncIsRepeatedWhenTheWorkerChangesBeforeTheAnswer(t *testing.T) {
	assert := assert.New(t)

	w := newWorkers(t, 100)
	svc := newResyncSvc(t, w)
	svc.RecordWorkerPid()

	changed := false
	reqs, _ := apiv4(t, svc, func(haproxysync.ResyncRequest) (string, bool) {
		if !changed {
			changed = true
			w.set(101)
		}
		return "", true
	})

	first, second := next(t, reqs), next(t, reqs)
	assert.Equal(haproxysync.ResyncReasonStarted, first.Reason)
	assert.Equal(haproxysync.ResyncReasonStarted, second.Reason)
	assert.Greater(second.ID, first.ID)
	quiet(t, svc, reqs)
	assert.Equal(101, svc.WorkerPid())
}

// After a reload haproxy-sync was not told about, the next reload sees the old worker as new.
func TestAReloadAfterAnUnsignalledReloadReachesTheNewWorker(t *testing.T) {
	assert := assert.New(t)

	w := newWorkers(t, 100)
	svc := newResyncSvc(t, w)
	svc.RecordWorkerPid()

	reqs, _ := apiv4(t, svc, func(r haproxysync.ResyncRequest) (string, bool) {
		if r.Reason == haproxysync.ResyncReasonReload {
			// the new worker takes the socket while apiv4 is pushing
			w.set(102)
		}
		return "", true
	})
	next(t, reqs)
	idle(t, svc)

	// the unsignalled reload: 101 replaces 100 and nobody tells haproxy-sync
	w.set(101)
	// the normal reload: 101 still answers when the signal arrives
	svc.NotifyReload(t.Context())

	assert.Equal(haproxysync.ResyncReasonReload, next(t, reqs).Reason)
	assert.Equal(haproxysync.ResyncReasonReload, next(t, reqs).Reason)
	quiet(t, svc, reqs)
	assert.Equal(102, svc.WorkerPid())
}

func TestAFailedResyncIsRetriedUntilItSucceeds(t *testing.T) {
	assert := assert.New(t)

	svc := newResyncSvc(t, newWorkers(t, 7))

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
	quiet(t, svc, reqs)
}

func TestAnUnansweredResyncIsRetried(t *testing.T) {
	svc := newResyncSvc(t, newWorkers(t, 7))
	svc.SetResyncTimings(200*time.Millisecond, time.Millisecond, 4*time.Millisecond)

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
	quiet(t, svc, reqs)
}

// A resync slower than the ack timeout still ends its cycle.
func TestALateAnswerToAnEarlierRequestEndsTheCycle(t *testing.T) {
	assert := assert.New(t)

	svc := newResyncSvc(t, newWorkers(t, 7))
	svc.SetResyncTimings(200*time.Millisecond, time.Millisecond, 4*time.Millisecond)

	var first uint64
	reqs, _ := apiv4(t, svc, func(r haproxysync.ResyncRequest) (string, bool) {
		switch {
		case first == 0:
			// the slow resync: no answer before the timeout
			first = r.ID
		case r.ID == first+1:
			// it finishes once the request was already repeated
			svc.AckResync(first, "")
		}
		return "", false
	})

	next(t, reqs)
	next(t, reqs)
	quiet(t, svc, reqs)
	assert.Equal(7, svc.WorkerPid())
}

func TestAFailureOfAnEarlierRequestDoesNotCountForTheNewestOne(t *testing.T) {
	svc := newResyncSvc(t, newWorkers(t, 7))
	svc.SetResyncTimings(200*time.Millisecond, time.Millisecond, 4*time.Millisecond)

	var first uint64
	reqs, _ := apiv4(t, svc, func(r haproxysync.ResyncRequest) (string, bool) {
		if first == 0 {
			first = r.ID
			return "", false
		}
		// the stale failure arrives first and must not start a third request
		svc.AckResync(first, "rethinkdb down")
		return "", true
	})

	first2, second := next(t, reqs), next(t, reqs)
	assert.Equal(t, first2.ID+1, second.ID)
	quiet(t, svc, reqs)
}

func TestAReloadReplacesTheResyncBeingRetried(t *testing.T) {
	require := require.New(t)

	w := newWorkers(t, 7)
	svc := newResyncSvc(t, w)
	svc.RecordWorkerPid()

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

	w.set(8)
	svc.NotifyReload(t.Context())

	r := next(t, reqs)
	for r.Reason == haproxysync.ResyncReasonStarted {
		r = next(t, reqs)
	}
	require.Equal(haproxysync.ResyncReasonReload, r.Reason)
	require.Equal(haproxysync.ResyncReasonReload, next(t, reqs).Reason)
	quiet(t, svc, reqs)
}

func TestAReconnectedWatcherGetsTheResyncThatFailed(t *testing.T) {
	svc := newResyncSvc(t, newWorkers(t, 7))

	failing, closeFailing := apiv4(t, svc, func(haproxysync.ResyncRequest) (string, bool) {
		return "connection reset", true
	})
	next(t, failing)
	closeFailing()

	reqs, _ := apiv4(t, svc, succeed)
	assert.Equal(t, haproxysync.ResyncReasonReopened, next(t, reqs).Reason)
	quiet(t, svc, reqs)
}
