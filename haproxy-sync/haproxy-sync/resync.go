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

	// above apiv4's DomainSync deadline, which leaves acme.sh ten minutes
	resyncAckTimeout = 15 * time.Minute
	resyncMinBackoff = time.Second
	resyncMaxBackoff = time.Minute
)

type ResyncRequest struct {
	ID     uint64
	Reason string
}

type resyncAck struct {
	id      uint64
	syncErr string
}

// resyncCycle lasts until a request it sent, any id from firstID on, is answered with success.
type resyncCycle struct {
	firstID uint64
	done    chan resyncAck
}

type resyncHub struct {
	mux       sync.Mutex
	subs      map[chan ResyncRequest]struct{}
	opened    bool
	workerPid int

	lastID  uint64
	cycle   *resyncCycle
	stop    context.CancelFunc
	running int

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

	c := h.resync.cycle
	if c == nil || id < c.firstID || id > h.resync.lastID {
		h.log.Debug().Uint64("id", id).Str("error", syncErr).Msg("ignoring the answer to a request of a superseded resync")
		return
	}

	if syncErr != "" && id != h.resync.lastID {
		h.log.Debug().Uint64("id", id).Str("error", syncErr).Msg("ignoring a failure already being retried")
		return
	}

	select {
	case c.done <- resyncAck{id: id, syncErr: syncErr}:
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
	c := &resyncCycle{firstID: h.resync.lastID + 1, done: make(chan resyncAck, 4)}
	h.resync.cycle = c
	h.resync.running++

	go func() {
		defer func() {
			h.resync.mux.Lock()
			h.resync.running--
			h.resync.mux.Unlock()
		}()

		h.resyncUntilAcked(ctx, c, reason)
	}()
}

func (h *HAproxySync) resyncUntilAcked(ctx context.Context, c *resyncCycle, reason string) {
	h.resync.mux.Lock()
	backoff, maxBackoff, ackTimeout := h.resync.minBackoff, h.resync.maxBackoff, h.resync.ackTimeout
	h.resync.mux.Unlock()

	// the worker answering when each request was sent
	workers := map[uint64]int{}

	for attempt := 1; ; attempt++ {
		pid, pidErr := h.haproxy.ShowPid()

		id, watchers, ok := h.broadcastResync(ctx, reason, attempt)
		if !ok {
			return
		}
		if watchers == 0 {
			h.log.Warn().Str("reason", reason).Int("attempt", attempt).Msg("no resync watcher connected, the next one to connect gets a resync")
			return
		}
		if pidErr == nil {
			workers[id] = pid
		}

		var failure error
		select {
		case <-ctx.Done():
			return

		case ack := <-c.done:
			if ack.syncErr != "" {
				failure = errors.New(ack.syncErr)
				break
			}

			now, err := h.sameWorker(workers, ack.id)
			if err == nil {
				h.resync.mux.Lock()
				h.resync.workerPid = now
				h.resync.mux.Unlock()

				h.log.Info().Str("reason", reason).Uint64("id", ack.id).Int("attempt", attempt).Int("pid", now).Msg("resync done")
				return
			}
			failure = err

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

// sameWorker fails when the worker changed since request id: the push went to the old one.
func (h *HAproxySync) sameWorker(workers map[uint64]int, id uint64) (int, error) {
	before, ok := workers[id]
	if !ok {
		return 0, errors.New("the HAProxy worker was unknown when the request was sent")
	}

	now, err := h.haproxy.ShowPid()
	if err != nil {
		return 0, fmt.Errorf("read the HAProxy worker after the resync: %w", err)
	}

	if now != before {
		return 0, fmt.Errorf("the HAProxy worker changed from %d to %d during the resync", before, now)
	}

	return now, nil
}

// broadcastResync sends a new request to every watcher, unless ctx was superseded meanwhile.
func (h *HAproxySync) broadcastResync(ctx context.Context, reason string, attempt int) (uint64, int, bool) {
	h.resync.mux.Lock()
	defer h.resync.mux.Unlock()

	if ctx.Err() != nil {
		return 0, 0, false
	}

	h.resync.lastID++
	r := ResyncRequest{ID: h.resync.lastID, Reason: reason}
	for ch := range h.resync.subs {
		// a request still unread is stale: keep only the newest
		select {
		case <-ch:
		default:
		}
		ch <- r
	}

	h.log.Info().Str("reason", reason).Uint64("id", r.ID).Int("attempt", attempt).Int("watchers", len(h.resync.subs)).Msg("resync requested")

	return r.ID, len(h.resync.subs), true
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
