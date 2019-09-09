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
	lastAccessedTime time.Time
}

func NewHttpTunnel(tunnel Tunnel) (ret HttpTunnel) {
	ret.Tunnel = tunnel
	ret.Access()
	return
}

func (opt *HttpTunnel) Access() {
	opt.lastAccessedTime = time.Now()
}

func (opt *HttpTunnel) GetLastAccessedTime() time.Time {
	return opt.lastAccessedTime
}
