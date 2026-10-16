package haproxysync

import (
	"context"
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
)

type resyncHub struct {
	mux       sync.Mutex
	subs      map[chan string]struct{}
	opened    bool
	workerPid int
}

func (h *HAproxySync) WatchResync(ctx context.Context, send func(reason string) error) error {
	ch := make(chan string, 1)

	h.resync.mux.Lock()
	reason := ResyncReasonReopened
	if !h.resync.opened {
		reason = ResyncReasonStarted
		h.resync.opened = true
	}
	h.resync.subs[ch] = struct{}{}
	h.resync.mux.Unlock()

	defer func() {
		h.resync.mux.Lock()
		delete(h.resync.subs, ch)
		h.resync.mux.Unlock()
	}()

	h.log.Info().Str("reason", reason).Msg("resync watcher connected, asking for a resync")
	if err := send(reason); err != nil {
		return err
	}

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

func (h *HAproxySync) requestResync(reason string) {
	h.resync.mux.Lock()
	defer h.resync.mux.Unlock()

	for ch := range h.resync.subs {
		select {
		case ch <- reason:
		default:
		}
	}

	h.log.Info().Str("reason", reason).Int("watchers", len(h.resync.subs)).Msg("resync requested")
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

	h.requestResync(ResyncReasonReload)
}
