package guac

import (
	uuid "github.com/satori/go.uuid"
	"io"
)

// DelegatingTunnel ==> Tunnel
//  * Tunnel implementation which simply delegates all function calls to
//  * an underlying Tunnel.
type DelegatingTunnel struct {
	tunnel Tunnel
}

// NewDelegatingTunnel Construct
func NewDelegatingTunnel(tunnel Tunnel) (ret DelegatingTunnel) {
	ret.tunnel = tunnel
	return
}

// GetUUID override Tunnel.GetUUID
func (opt *DelegatingTunnel) GetUUID() uuid.UUID {
	return opt.tunnel.GetUUID()
}

// GetSocket override Tunnel.GetSocket
func (opt *DelegatingTunnel) GetSocket() Socket {
	return opt.tunnel.GetSocket()
}

// AcquireReader override Tunnel.AcquireReader
func (opt *DelegatingTunnel) AcquireReader() Reader {
	return opt.tunnel.AcquireReader()
}

// ReleaseReader override Tunnel.ReleaseReader
func (opt *DelegatingTunnel) ReleaseReader() {
	opt.tunnel.ReleaseReader()
}

// HasQueuedReaderThreads override Tunnel.HasQueuedReaderThreads
func (opt *DelegatingTunnel) HasQueuedReaderThreads() bool {
	return opt.tunnel.HasQueuedReaderThreads()
}

// AcquireWriter override Tunnel.AcquireWriter
func (opt *DelegatingTunnel) AcquireWriter() io.Writer {
	return opt.tunnel.AcquireWriter()
}

// ReleaseWriter override Tunnel.ReleaseWriter
func (opt *DelegatingTunnel) ReleaseWriter() {
	opt.tunnel.ReleaseWriter()
}

// HasQueuedWriterThreads override Tunnel.HasQueuedWriterThreads
func (opt *DelegatingTunnel) HasQueuedWriterThreads() bool {
	return opt.tunnel.HasQueuedWriterThreads()
}

// Close override Tunnel.Close
func (opt *DelegatingTunnel) Close() error {
	return opt.tunnel.Close()
}

// IsOpen override Tunnel.IsOpen
func (opt *DelegatingTunnel) IsOpen() bool {
	if opt.tunnel != nil {
		return opt.tunnel.IsOpen()
	}
	return false
}
