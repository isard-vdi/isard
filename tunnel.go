package guac

import (
	"github.com/satori/go.uuid"
	"io"
)

//  * The Guacamole protocol instruction Opcode reserved for arbitrary
//  * internal use by tunnel implementations. The value of this Opcode is
//  * guaranteed to be the empty string (""). Tunnel implementations may use
//  * this Opcode for any purpose. It is currently used by the HTTP tunnel to
//  * mark the end of the HTTP response, and by the WebSocket tunnel to
//  * transmit the tunnel UUID.
const InternalDataOpcode = ""

// Tunnel provides a unique identifier and synchronized access to the Reader and Writer associated with a Socket.
type Tunnel interface {
	AcquireReader() *InstructionReader
	ReleaseReader()
	HasQueuedReaderThreads() bool
	AcquireWriter() io.Writer
	ReleaseWriter()
	HasQueuedWriterThreads() bool
	GetUUID() uuid.UUID
	GetSocket() *Socket
	Close() error
}

//  * Base Tunnel implementation which synchronizes access to the
//  * underlying reader and writer with reentrant locks. Implementations need only
//  * provide the tunnel's UUID and socket.
type SimpleTunnel struct {
	socket *Socket
	/**
	 * The UUID associated with this tunnel. Every tunnel must have a
	 * corresponding UUID such that tunnel read/write requests can be
	 * directed to the proper tunnel.
	 */
	uuid       uuid.UUID
	readerLock CountedLock
	writerLock CountedLock
}

// NewSimpleTunnel Construct function
func NewSimpleTunnel(socket *Socket) *SimpleTunnel {
	return &SimpleTunnel{
		socket: socket,
		uuid:   uuid.NewV4(),
	}
}

// AcquireReader override Tunnel.AcquireReader
func (t *SimpleTunnel) AcquireReader() *InstructionReader {
	t.readerLock.Lock()
	return t.socket.InstructionReader
}

// ReleaseReader override Tunnel.ReleaseReader
func (t *SimpleTunnel) ReleaseReader() {
	t.readerLock.Unlock()
}

// HasQueuedReaderThreads override Tunnel.HasQueuedReaderThreads
func (t *SimpleTunnel) HasQueuedReaderThreads() bool {
	return t.readerLock.HasQueued()
}

// AcquireWriter override Tunnel.AcquireWriter
func (t *SimpleTunnel) AcquireWriter() io.Writer {
	t.writerLock.Lock()
	return t.socket
}

// ReleaseWriter override Tunnel.ReleaseWriter
func (t *SimpleTunnel) ReleaseWriter() {
	t.writerLock.Unlock()
}

// HasQueuedWriterThreads override Tunnel.HasQueuedWriterThreads
func (t *SimpleTunnel) HasQueuedWriterThreads() bool {
	return t.writerLock.HasQueued()
}

// Close override Tunnel.Close
func (t *SimpleTunnel) Close() (err error) {
	if t.socket != nil {
		err = t.socket.Close()
	} else {
		err = ErrConnectionClosed.NewError("Closed")
	}
	return
}

// GetUUID override Tunnel.GetUUID
func (t *SimpleTunnel) GetUUID() uuid.UUID {
	return t.uuid
}

// GetSocket override Tunnel.GetSocket
func (t *SimpleTunnel) GetSocket() *Socket {
	return t.socket
}
