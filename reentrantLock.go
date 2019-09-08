package guac

// Becareful here
// Using sync/* to instead java.ReentrantLock
// That means change whole work design
// Fortunately, there is nothing need to re-enter in java
// So we just add `HasQueuedThreads`

import (
	"sync"
	"sync/atomic"
)

// ReentrantLock is NOT a re-enterant-lock
// Just add HasQueuedThreads method
type ReentrantLock struct {
	core   sync.Mutex
	requir int32
}

// Lock override ReentrantLock.Lock
func (r *ReentrantLock) Lock() {
	atomic.AddInt32(&r.requir, 1)
	r.core.Lock()
}

// Unlock override ReentrantLock.Unlock
func (r *ReentrantLock) Unlock() {
	atomic.AddInt32(&r.requir, -1)
	r.core.Unlock()
}

// HasQueuedThreads override ReentrantLock.HasQueuedThreads
func (r *ReentrantLock) HasQueuedThreads() bool {
	return atomic.LoadInt32(&r.requir) > 1
}
