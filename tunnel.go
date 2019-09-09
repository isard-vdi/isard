package guac

import "github.com/satori/go.uuid"

//  * The Guacamole protocol instruction opcode reserved for arbitrary
//  * internal use by tunnel implementations. The value of this opcode is
//  * guaranteed to be the empty string (""). Tunnel implementations may use
//  * this opcode for any purpose. It is currently used by the HTTP tunnel to
//  * mark the end of the HTTP response, and by the WebSocket tunnel to
//  * transmit the tunnel UUID.
const InternalDataOpcode = ""

// Tunnel provides a unique identifier and synchronized access to the Reader and Writer associated with a Socket.
type Tunnel interface {
	AcquireReader() Reader
	ReleaseReader()
	HasQueuedReaderThreads() bool
	AcquireWriter() Writer
	ReleaseWriter()
	HasQueuedWriterThreads() bool
	GetUUID() uuid.UUID
	GetSocket() Socket
	Close() error
	IsOpen() bool
}

//  * Base Tunnel implementation which synchronizes access to the
//  * underlying reader and writer with reentrant locks. Implementations need only
//  * provide the tunnel's UUID and socket.
type SimpleTunnel struct {
	socket Socket
	/**
	 * The UUID associated with this tunnel. Every tunnel must have a
	 * corresponding UUID such that tunnel read/write requests can be
	 * directed to the proper tunnel.
	 */
	uuid       uuid.UUID
	readerLock ReentrantLock
	writerLock ReentrantLock
}

// NewSimpleTunnel Construct function
func NewSimpleTunnel(core Socket) *SimpleTunnel {
	return &SimpleTunnel{
		socket: core,
		uuid:   uuid.NewV4(),
	}
}

// AcquireReader override Tunnel.AcquireReader
func (t *SimpleTunnel) AcquireReader() Reader {
	t.readerLock.Lock()
	return t.socket.GetReader()
}

// ReleaseReader override Tunnel.ReleaseReader
func (t *SimpleTunnel) ReleaseReader() {
	t.readerLock.Unlock()
}

// HasQueuedReaderThreads override Tunnel.HasQueuedReaderThreads
func (t *SimpleTunnel) HasQueuedReaderThreads() bool {
	return t.readerLock.HasQueuedThreads()
}

// AcquireWriter override Tunnel.AcquireWriter
func (t *SimpleTunnel) AcquireWriter() Writer {
	t.writerLock.Lock()
	return t.socket.GetWriter()
}

// ReleaseWriter override Tunnel.ReleaseWriter
func (t *SimpleTunnel) ReleaseWriter() {
	t.writerLock.Unlock()
}

// HasQueuedWriterThreads override Tunnel.HasQueuedWriterThreads
func (t *SimpleTunnel) HasQueuedWriterThreads() bool {
	return t.writerLock.HasQueuedThreads()
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

// IsOpen override Tunnel.IsOpen
func (t *SimpleTunnel) IsOpen() bool {
	if t.socket != nil {
		return t.socket.IsOpen()
	}
	return false
}

// GetUUID override Tunnel.GetUUID
func (t *SimpleTunnel) GetUUID() uuid.UUID {
	return t.uuid
}

// GetSocket override Tunnel.GetSocket
func (t *SimpleTunnel) GetSocket() Socket {
	return t.socket
}
