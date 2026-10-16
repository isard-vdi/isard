package haproxysync

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

const (
	ResyncReasonStarted  = "haproxy-sync started"
	ResyncReasonReopened = "stream reopened"
	ResyncReasonReload   = "haproxy reload"
)

const (
	reloadWaitTimeout  = 10 * time.Second
	reloadPollInterval = 100 * time.Millisecond

	// a resync can issue ACME certificates, so the answer may take minutes
	resyncAckTimeout = 5 * time.Minute
	resyncMinBackoff = time.Second
	resyncMaxBackoff = time.Minute
)

type ResyncRequest struct {
	ID     uint64
	Reason string
}

type resyncAttempt struct {
	id   uint64
	done chan string
}

type resyncHub struct {
	mux       sync.Mutex
	subs      map[chan ResyncRequest]struct{}
	opened    bool
	workerPid int

	lastID  uint64
	attempt *resyncAttempt
	stop    context.CancelFunc

	ackTimeout time.Duration
	minBackoff time.Duration
	maxBackoff time.Duration
}

func newResyncHub() resyncHub {
	return resyncHub{
		subs:       map[chan ResyncRequest]struct{}{},
		ackTimeout: resyncAckTimeout,
		minBackoff: resyncMinBackoff,
		maxBackoff: resyncMaxBackoff,
	}
}

func (h *HAproxySync) WatchResync(ctx context.Context, send func(ResyncRequest) error) error {
	ch := make(chan ResyncRequest, 1)

	h.resync.mux.Lock()
	reason := ResyncReasonReopened
	if !h.resync.opened {
		reason = ResyncReasonStarted
		h.resync.opened = true
	}
	h.resync.subs[ch] = struct{}{}
	h.startResyncLocked(reason)
	h.resync.mux.Unlock()

	defer func() {
		h.resync.mux.Lock()
		delete(h.resync.subs, ch)
		h.resync.mux.Unlock()
	}()

	h.log.Info().Str("reason", reason).Msg("resync watcher connected, asking for a resync")

	for {
		select {
		case <-ctx.Done():
			return nil

		case r := <-ch:
			if err := send(r); err != nil {
				return err
			}
		}
	}
}

func (h *HAproxySync) AckResync(id uint64, syncErr string) {
	h.resync.mux.Lock()
	defer h.resync.mux.Unlock()

	if h.resync.attempt == nil || h.resync.attempt.id != id {
		h.log.Debug().Uint64("id", id).Str("error", syncErr).Msg("ignoring the answer to a superseded resync request")
		return
	}

	select {
	case h.resync.attempt.done <- syncErr:
	default:
	}
}

// startResyncLocked replaces the running resync cycle, if any, with a new one for reason.
func (h *HAproxySync) startResyncLocked(reason string) {
	if h.resync.stop != nil {
		h.resync.stop()
	}

	ctx, stop := context.WithCancel(context.Background())
	h.resync.stop = stop
	h.resync.attempt = nil

	go h.resyncUntilAcked(ctx, reason)
}

func (h *HAproxySync) resyncUntilAcked(ctx context.Context, reason string) {
	h.resync.mux.Lock()
	backoff, maxBackoff, ackTimeout := h.resync.minBackoff, h.resync.maxBackoff, h.resync.ackTimeout
	h.resync.mux.Unlock()

	for attempt := 1; ; attempt++ {
		id, done, watchers, ok := h.broadcastResync(ctx, reason, attempt)
		if !ok {
			return
		}
		if watchers == 0 {
			h.log.Warn().Str("reason", reason).Int("attempt", attempt).Msg("no resync watcher connected, the next one to connect gets a resync")
			return
		}

		var failure error
		select {
		case <-ctx.Done():
			return

		case syncErr := <-done:
			if syncErr == "" {
				h.log.Info().Str("reason", reason).Uint64("id", id).Int("attempt", attempt).Msg("resync done")
				return
			}
			failure = errors.New(syncErr)

		case <-time.After(ackTimeout):
			failure = fmt.Errorf("no answer after %s", ackTimeout)
		}

		h.log.Warn().Err(failure).Str("reason", reason).Uint64("id", id).Int("attempt", attempt).Dur("retry_in", backoff).Msg("resync failed, retrying")

		select {
		case <-ctx.Done():
			return
		case <-time.After(backoff):
		}
		backoff = min(backoff*2, maxBackoff)
	}
}

// broadcastResync sends a new request to every watcher, unless ctx was superseded meanwhile.
func (h *HAproxySync) broadcastResync(ctx context.Context, reason string, attempt int) (uint64, <-chan string, int, bool) {
	h.resync.mux.Lock()
	defer h.resync.mux.Unlock()

	if ctx.Err() != nil {
		return 0, nil, 0, false
	}

	h.resync.lastID++
	a := &resyncAttempt{id: h.resync.lastID, done: make(chan string, 1)}
	h.resync.attempt = a

	r := ResyncRequest{ID: a.id, Reason: reason}
	for ch := range h.resync.subs {
		// a request still unread is stale: keep only the newest
		select {
		case <-ch:
		default:
		}
		ch <- r
	}

	h.log.Info().Str("reason", reason).Uint64("id", a.id).Int("attempt", attempt).Int("watchers", len(h.resync.subs)).Msg("resync requested")

	return a.id, a.done, len(h.resync.subs), true
}

// RecordWorkerPid remembers the worker currently answering, so NotifyReload can tell when it changes.
func (h *HAproxySync) RecordWorkerPid() {
	pid, err := h.haproxy.ShowPid()
	if err != nil {
		h.log.Warn().Err(err).Msg("read the HAProxy worker pid")
		return
	}

	h.resync.mux.Lock()
	h.resync.workerPid = pid
	h.resync.mux.Unlock()
}

// NotifyReload waits for the new worker before asking for a resync: entries sent earlier would
// land in the worker that is shutting down.
func (h *HAproxySync) NotifyReload(ctx context.Context) {
	h.resync.mux.Lock()
	previous := h.resync.workerPid
	h.resync.mux.Unlock()

	deadline := time.Now().Add(reloadWaitTimeout)
	for {
		pid, err := h.haproxy.ShowPid()
		if err == nil && pid != previous {
			h.resync.mux.Lock()
			h.resync.workerPid = pid
			h.resync.mux.Unlock()

			break
		}

		if time.Now().After(deadline) {
			h.log.Warn().Int("pid", previous).Msg("no new HAProxy worker after the reload signal, resyncing anyway")
			break
		}

		select {
		case <-ctx.Done():
			return
		case <-time.After(reloadPollInterval):
		}
	}

	h.resync.mux.Lock()
	h.startResyncLocked(ResyncReasonReload)
	h.resync.mux.Unlock()
}
