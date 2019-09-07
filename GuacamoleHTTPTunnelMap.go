package guac

import (
	logger "github.com/sirupsen/logrus"
	"sync"
	"time"
)

// log instead of LoggerFactory

/*TunnelTimeout *
 * The number of seconds to wait between tunnel accesses before timing out
 * Note that this will be enforced only within a factor of 2. If a tunnel
 * is unused, it will take between TUNNEL_TIMEOUT and TUNNEL_TIMEOUT*2
 * seconds before that tunnel is closed and removed.
 */
const TunnelTimeout = 15 * time.Second

/*GuacamoleHTTPTunnelMap *
 * Map-style object which tracks in-use HTTP tunnels, automatically removing
 * and closing tunnels which have not been used recently. This class is
 * intended for use only within the GuacamoleHTTPTunnelServlet implementation,
 * and has no real utility outside that implementation.
 */
type GuacamoleHTTPTunnelMap struct {
	/**
	 * Executor service which runs the periodic tunnel timeout task.
	 */
	executor []*time.Ticker

	/**
	 * The maximum amount of time to allow between accesses to any one
	 * HTTP tunnel, in milliseconds.
	 */
	tunnelTimeout time.Duration

	/**
	 * Map of all tunnels that are using HTTP, indexed by tunnel UUID.
	 */
	tunnelMap     map[string]*GuacamoleHTTPTunnel
	tunnelMapLock sync.RWMutex
}

/*NewGuacamoleHTTPTunnelMap *
 * Creates a new GuacamoleHTTPTunnelMap which automatically closes and
 * removes HTTP tunnels which are no longer in use.
 */
func NewGuacamoleHTTPTunnelMap() (ret GuacamoleHTTPTunnelMap) {

	ret.executor = make([]*time.Ticker, 0, 1)
	ret.tunnelMap = make(map[string]*GuacamoleHTTPTunnel)

	ret.tunnelTimeout = TunnelTimeout

	ret.startScheduled(1, TunnelTimeout)
	return
}

func (opt *GuacamoleHTTPTunnelMap) startScheduled(count int32, timeout time.Duration) {
	for i := int32(len(opt.executor)); i < count; i++ {

		tick := time.NewTicker(timeout)
		go opt.tunnelTimeoutTask(tick.C)

		opt.executor = append(opt.executor, tick)
	}
}

func (opt *GuacamoleHTTPTunnelMap) tunnelTimeoutTask(c <-chan time.Time) {
	for {
		_, ok := <-c
		if !ok {
			break
		}
		opt.tunnelTimeoutTaskRun()
	}
}

func (opt *GuacamoleHTTPTunnelMap) tunnelTimeoutTaskRun() {
	// timeLine = Now() - tunnelTimeout
	timeLine := time.Now().Add(0 - opt.tunnelTimeout)

	type pair struct {
		uuid   string
		tunnel *GuacamoleHTTPTunnel
	}
	removeIDs := make([]pair, 0, 1)

	opt.tunnelMapLock.RLock()
	for uuid, tunnel := range opt.tunnelMap {
		if tunnel.GetLastAccessedTime().Before(timeLine) {
			removeIDs = append(removeIDs, pair{uuid: uuid, tunnel: tunnel})
		}
	}
	opt.tunnelMapLock.RUnlock()

	for _, double := range removeIDs {
		logger.Debugf("HTTP tunnel \"%v\" has timed out.", double.uuid)
		opt.tunnelMapLock.Lock()
		delete(opt.tunnelMap, double.uuid)
		opt.tunnelMapLock.Unlock()

		if double.tunnel != nil {
			err := double.tunnel.Close()
			if err != nil {
				logger.Debug("Unable to close expired HTTP tunnel.", err)
			}
		}
	}
	return
}

/*Get *
 * Returns the GuacamoleTunnel having the given UUID, wrapped within a
 * GuacamoleHTTPTunnel. If the no tunnel having the given UUID is
 * available, null is returned.
 *
 * @param uuid
 *     The UUID of the tunnel to retrieve.
 *
 * @return
 *     The GuacamoleTunnel having the given UUID, wrapped within a
 *     GuacamoleHTTPTunnel, if such a tunnel exists, or null if there is no
 *     such tunnel.
 */
func (opt *GuacamoleHTTPTunnelMap) Get(uuid string) (tunnel *GuacamoleHTTPTunnel, ok bool) {

	// Update the last access time
	opt.tunnelMapLock.RLock()
	tunnel, ok = opt.tunnelMap[uuid]
	opt.tunnelMapLock.RUnlock()

	if ok && tunnel != nil {
		tunnel.Access()
	} else {
		ok = false
	}

	// Return tunnel, if any
	return

}

/*Put *
 * Registers that a new connection has been established using HTTP via the
 * given GuacamoleTunnel.
 *
 * @param uuid
 *     The UUID of the tunnel being added (registered).
 *
 * @param tunnel
 *     The GuacamoleTunnel being registered, its associated connection
 *     having just been established via HTTP.
 */
func (opt *GuacamoleHTTPTunnelMap) Put(uuid string, tunnel GuacamoleTunnel) {
	one := NewGuacamoleHTTPTunnel(tunnel)
	opt.tunnelMapLock.Lock()
	opt.tunnelMap[uuid] = &one
	opt.tunnelMapLock.Unlock()
}

/*Remove *
 * Removes the GuacamoleTunnel having the given UUID, if such a tunnel
 * exists. The original tunnel is returned wrapped within a
 * GuacamoleHTTPTunnel.
 *
 * @param uuid
 *     The UUID of the tunnel to remove (deregister).
 *
 * @return
 *     The GuacamoleTunnel having the given UUID, if such a tunnel exists,
 *     wrapped within a GuacamoleHTTPTunnel, or null if no such tunnel
 *     exists and no removal was performed.
 */
func (opt *GuacamoleHTTPTunnelMap) Remove(uuid string) (*GuacamoleHTTPTunnel, bool) {

	opt.tunnelMapLock.RLock()
	v, ok := opt.tunnelMap[uuid]
	opt.tunnelMapLock.RUnlock()

	if ok {
		opt.tunnelMapLock.Lock()
		delete(opt.tunnelMap, uuid)
		opt.tunnelMapLock.Unlock()
	}
	return v, ok
}

/*Shutdown *
 * Shuts down this tunnel map, disallowing future tunnels from being
 * registered and reclaiming any resources.
 */
func (opt *GuacamoleHTTPTunnelMap) Shutdown() {
	for _, c := range opt.executor {
		c.Stop()
	}
	opt.executor = make([]*time.Ticker, 0, 1)
}
