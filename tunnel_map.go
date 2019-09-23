package guac

import (
	"github.com/sirupsen/logrus"
	"sync"
	"time"
)

/*LastAccessedTunnel
 * Tracks the last time a particular Tunnel was accessed. This
 * information is not necessary for tunnels associated with WebSocket
 * connections, as each WebSocket connection has its own read thread which
 * continuously checks the state of the tunnel and which will automatically
 * timeout when the underlying stream times out, but the HTTP tunnel has no
 * such thread. Because the HTTP tunnel requires the stream to be split across
 * multiple requests, tracking of activity on the tunnel must be performed
 * independently of the HTTP requests.
 */
type LastAccessedTunnel struct {
	Tunnel
	lastAccessedTime time.Time
}

func NewLastAccessedTunnel(tunnel Tunnel) (ret LastAccessedTunnel) {
	ret.Tunnel = tunnel
	ret.Access()
	return
}

func (t *LastAccessedTunnel) Access() {
	t.lastAccessedTime = time.Now()
}

func (t *LastAccessedTunnel) GetLastAccessedTime() time.Time {
	return t.lastAccessedTime
}

/*TunnelTimeout *
 * The number of seconds to wait between tunnel accesses before timing out
 * Note that this will be enforced only within a factor of 2. If a tunnel
 * is unused, it will take between TUNNEL_TIMEOUT and TUNNEL_TIMEOUT*2
 * seconds before that tunnel is closed and removed.
 */
const TunnelTimeout = 15 * time.Second

/*TunnelMap *
 * Map-style object which tracks in-use HTTP tunnels, automatically removing
 * and closing tunnels which have not been used recently. This class is
 * intended for use only within the Server implementation,
 * and has no real utility outside that implementation.
 */
type TunnelMap struct {
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
	tunnelMap     map[string]*LastAccessedTunnel
	tunnelMapLock sync.RWMutex
}

/*NewTunnelMap *
 * Creates a new TunnelMap which automatically closes and
 * removes HTTP tunnels which are no longer in use.
 */
func NewTunnelMap() (ret TunnelMap) {

	ret.executor = make([]*time.Ticker, 0, 1)
	ret.tunnelMap = make(map[string]*LastAccessedTunnel)

	ret.tunnelTimeout = TunnelTimeout

	ret.startScheduled(1, TunnelTimeout)
	return
}

func (m *TunnelMap) startScheduled(count int32, timeout time.Duration) {
	for i := int32(len(m.executor)); i < count; i++ {

		tick := time.NewTicker(timeout)
		go m.tunnelTimeoutTask(tick.C)

		m.executor = append(m.executor, tick)
	}
}

func (m *TunnelMap) tunnelTimeoutTask(c <-chan time.Time) {
	for {
		_, ok := <-c
		if !ok {
			break
		}
		m.tunnelTimeoutTaskRun()
	}
}

func (m *TunnelMap) tunnelTimeoutTaskRun() {
	// timeLine = Now() - tunnelTimeout
	timeLine := time.Now().Add(0 - m.tunnelTimeout)

	type pair struct {
		uuid   string
		tunnel *LastAccessedTunnel
	}
	removeIDs := make([]pair, 0, 1)

	m.tunnelMapLock.RLock()
	for uuid, tunnel := range m.tunnelMap {
		if tunnel.GetLastAccessedTime().Before(timeLine) {
			removeIDs = append(removeIDs, pair{uuid: uuid, tunnel: tunnel})
		}
	}
	m.tunnelMapLock.RUnlock()

	for _, double := range removeIDs {
		logrus.Debugf("HTTP tunnel \"%v\" has timed out.", double.uuid)
		m.tunnelMapLock.Lock()
		delete(m.tunnelMap, double.uuid)
		m.tunnelMapLock.Unlock()

		if double.tunnel != nil {
			err := double.tunnel.Close()
			if err != nil {
				logrus.Debug("Unable to close expired HTTP tunnel.", err)
			}
		}
	}
	return
}

/*Get *
 * Returns the Tunnel having the given UUID, wrapped within a
 * LastAccessedTunnel. If the no tunnel having the given UUID is
 * available, null is returned.
 *
 * @param uuid
 *     The UUID of the tunnel to retrieve.
 *
 * @return
 *     The Tunnel having the given UUID, wrapped within a
 *     LastAccessedTunnel, if such a tunnel exists, or null if there is no
 *     such tunnel.
 */
func (m *TunnelMap) Get(uuid string) (tunnel *LastAccessedTunnel, ok bool) {

	// Update the last access time
	m.tunnelMapLock.RLock()
	tunnel, ok = m.tunnelMap[uuid]
	m.tunnelMapLock.RUnlock()

	if ok && tunnel != nil {
		tunnel.Access()
	} else {
		ok = false
	}

	// Return tunnel, if any
	return

}

/*Add *
 * Registers that a new connection has been established using HTTP via the
 * given Tunnel.
 *
 * @param uuid
 *     The UUID of the tunnel being added (registered).
 *
 * @param tunnel
 *     The Tunnel being registered, its associated connection
 *     having just been established via HTTP.
 */
func (m *TunnelMap) Put(uuid string, tunnel Tunnel) {
	one := NewLastAccessedTunnel(tunnel)
	m.tunnelMapLock.Lock()
	m.tunnelMap[uuid] = &one
	m.tunnelMapLock.Unlock()
}

/*Remove *
 * Removes the Tunnel having the given UUID, if such a tunnel
 * exists. The original tunnel is returned wrapped within a
 * LastAccessedTunnel.
 *
 * @param uuid
 *     The UUID of the tunnel to remove (deregister).
 *
 * @return
 *     The Tunnel having the given UUID, if such a tunnel exists,
 *     wrapped within a LastAccessedTunnel, or null if no such tunnel
 *     exists and no removal was performed.
 */
func (m *TunnelMap) Remove(uuid string) (*LastAccessedTunnel, bool) {

	m.tunnelMapLock.RLock()
	v, ok := m.tunnelMap[uuid]
	m.tunnelMapLock.RUnlock()

	if ok {
		m.tunnelMapLock.Lock()
		delete(m.tunnelMap, uuid)
		m.tunnelMapLock.Unlock()
	}
	return v, ok
}

/*Shutdown *
 * Shuts down this tunnel map, disallowing future tunnels from being
 * registered and reclaiming any resources.
 */
func (m *TunnelMap) Shutdown() {
	for _, c := range m.executor {
		c.Stop()
	}
	m.executor = make([]*time.Ticker, 0, 1)
}
