package haproxysync

import "time"

func (h *HAproxySync) SetResyncTimings(ackTimeout, minBackoff, maxBackoff time.Duration) {
	h.resync.mux.Lock()
	defer h.resync.mux.Unlock()

	h.resync.ackTimeout = ackTimeout
	h.resync.minBackoff = minBackoff
	h.resync.maxBackoff = maxBackoff
}
