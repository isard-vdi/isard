package guac

import (
	"fmt"
	"github.com/satori/go.uuid"
	"io"
)

// The Guacamole protocol instruction Opcode reserved for arbitrary
// internal use by tunnel implementations. The value of this Opcode is
// guaranteed to be the empty string (""). Tunnel implementations may use
// this Opcode for any purpose. It is currently used by the HTTP tunnel to
// mark the end of the HTTP response, and by the WebSocket tunnel to
// transmit the tunnel UUID.
const InternalDataOpcode = ""

var internalOpcodeIns = fmt.Sprint(len(InternalDataOpcode), ".", InternalDataOpcode)

// InstructionReader provides reading functionality to a Stream
type InstructionReader interface {
	ReadSome() ([]byte, error)
	Available() bool
	Flush()
}

// Tunnel provides a unique identifier and synchronized access to the InstructionReader and Writer
// associated with a Stream.
type Tunnel interface {
	AcquireReader() InstructionReader
	ReleaseReader()
	HasQueuedReaderThreads() bool
	AcquireWriter() io.Writer
	ReleaseWriter()
	HasQueuedWriterThreads() bool
	GetUUID() string
	ConnectionID() string
	Close() error
}

// Base Tunnel implementation which synchronizes access to the underlying reader and writer with locks
type SimpleTunnel struct {
	stream *Stream
	/**
	 * The UUID associated with this tunnel. Every tunnel must have a
	 * corresponding UUID such that tunnel read/write requests can be
	 * directed to the proper tunnel.
	 */
	uuid       uuid.UUID
	readerLock CountedLock
	writerLock CountedLock
}

// NewSimpleTunnel creates a new tunnel
func NewSimpleTunnel(stream *Stream) *SimpleTunnel {
	return &SimpleTunnel{
		stream: stream,
		uuid:   uuid.NewV4(),
	}
}

// AcquireReader acquires the reader lock
func (t *SimpleTunnel) AcquireReader() InstructionReader {
	t.readerLock.Lock()
	return t.stream
}

// ReleaseReader releases the reader
func (t *SimpleTunnel) ReleaseReader() {
	t.readerLock.Unlock()
}

// HasQueuedReaderThreads returns true if more than one goroutine is trying to read
func (t *SimpleTunnel) HasQueuedReaderThreads() bool {
	return t.readerLock.HasQueued()
}

// AcquireWriter locks the writer lock
func (t *SimpleTunnel) AcquireWriter() io.Writer {
	t.writerLock.Lock()
	return t.stream
}

// ReleaseWriter releases the writer lock
func (t *SimpleTunnel) ReleaseWriter() {
	t.writerLock.Unlock()
}

// ConnectionID returns the underlying Guacamole connection ID
func (t *SimpleTunnel) ConnectionID() string {
	return t.stream.ConnectionID
}

// HasQueuedWriterThreads returns true if more than one goroutine is trying to write
func (t *SimpleTunnel) HasQueuedWriterThreads() bool {
	return t.writerLock.HasQueued()
}

// Close closes the underlying stream
func (t *SimpleTunnel) Close() (err error) {
	if t.stream != nil {
		err = t.stream.Close()
	} else {
		err = ErrConnectionClosed.NewError("Closed")
	}
	return
}

// GetUUID returns the tunnel's UUID
func (t *SimpleTunnel) GetUUID() string {
	return t.uuid.String()
}
