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

// NewReentrantLock Construct function
func NewReentrantLock() (ret ReentrantLock) {
	return
}

// Lock override ReentrantLock.Lock
func (opt *ReentrantLock) Lock() {
	atomic.AddInt32(&opt.requir, 1)
	opt.core.Lock()
}

// Unlock override ReentrantLock.Unlock
func (opt *ReentrantLock) Unlock() {
	atomic.AddInt32(&opt.requir, -1)
	opt.core.Unlock()
}

// HasQueuedThreads override ReentrantLock.HasQueuedThreads
func (opt *ReentrantLock) HasQueuedThreads() bool {
	return atomic.LoadInt32(&opt.requir) > 1
}
