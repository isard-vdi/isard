package haproxysync

import "time"

func (h *HAproxySync) SetResyncTimings(ackTimeout, minBackoff, maxBackoff time.Duration) {
	h.resync.mux.Lock()
	defer h.resync.mux.Unlock()

	h.resync.ackTimeout = ackTimeout
	h.resync.minBackoff = minBackoff
	h.resync.maxBackoff = maxBackoff
}

// ResyncIdle reports whether no resync cycle is running.
func (h *HAproxySync) ResyncIdle() bool {
	h.resync.mux.Lock()
	defer h.resync.mux.Unlock()

	return h.resync.running == 0
}

// WorkerPid is the HAProxy worker the last successful resync was confirmed against.
func (h *HAproxySync) WorkerPid() int {
	h.resync.mux.Lock()
	defer h.resync.mux.Unlock()

	return h.resync.workerPid
}
