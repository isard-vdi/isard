package guac

import (
	"time"
)

/*HttpTunnel ==> DelegatingTunnel
 * Tracks the last time a particular Tunnel was accessed. This
 * information is not necessary for tunnels associated with WebSocket
 * connections, as each WebSocket connection has its own read thread which
 * continuously checks the state of the tunnel and which will automatically
 * timeout when the underlying socket times out, but the HTTP tunnel has no
 * such thread. Because the HTTP tunnel requires the stream to be split across
 * multiple requests, tracking of activity on the tunnel must be performed
 * independently of the HTTP requests.
 */
type HttpTunnel struct {
	Tunnel
	/**
	 * The last time this tunnel was accessed.
	 */
	lastAccessedTime time.Time
}

/*NewHttpTunnel *
 * Creates a new HttpTunnel which wraps the given tunnel.
 * Absolutely all function calls on this new HttpTunnel will be
 * delegated to the underlying Tunnel.
 *
 * @param wrappedTunnel
 *     The Tunnel to wrap within this HttpTunnel.
 */
func NewHttpTunnel(tunnel Tunnel) (ret HttpTunnel) {
	ret.Tunnel = tunnel
	ret.Access()
	return
}

/*Access *
 * Updates this tunnel, marking it as recently accessed.
 */
func (opt *HttpTunnel) Access() {
	opt.lastAccessedTime = time.Now()
}

/*GetLastAccessedTime *
 * Returns the time this tunnel was last accessed, as the number of
 * milliseconds since midnight January 1, 1970 GMT. Tunnel access must
 * be explicitly marked through calls to the access() function.
 *
 * @return
 *     The time this tunnel was last accessed.
 */
func (opt *HttpTunnel) GetLastAccessedTime() time.Time {
	return opt.lastAccessedTime
}
