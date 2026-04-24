package provider

import (
	"sync"
)

// cfgManager is responsible for accessing / loading a provider
// runtime configuration
type cfgManager[T any] struct {
	mux sync.RWMutex

	cfg *T
}

func (c *cfgManager[T]) Cfg() T {
	c.mux.RLock()
	defer c.mux.RUnlock()

	return *c.cfg
}

func (c *cfgManager[T]) LoadCfg(cfg T) {
	c.mux.Lock()
	defer c.mux.Unlock()

	c.cfg = &cfg
}
