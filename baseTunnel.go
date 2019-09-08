package guac

// BaseTunnel ==> Tunnel
//  * Base Tunnel implementation which synchronizes access to the
//  * underlying reader and writer with reentrant locks. Implementations need only
//  * provide the tunnel's UUID and socket.
type BaseTunnel struct {
	core       GetSocketInterface
	readerLock ReentrantLock
	writerLock ReentrantLock
}

// NewBaseTunnel Construct function
func NewBaseTunnel(core GetSocketInterface) (ret BaseTunnel) {
	ret.core = core
	return
}

// AcquireReader override Tunnel.AcquireReader
func (t *BaseTunnel) AcquireReader() Reader {
	t.readerLock.Lock()
	return t.core.GetSocket().GetReader()
}

// ReleaseReader override Tunnel.ReleaseReader
func (t *BaseTunnel) ReleaseReader() {
	t.readerLock.Unlock()
}

// HasQueuedReaderThreads override Tunnel.HasQueuedReaderThreads
func (t *BaseTunnel) HasQueuedReaderThreads() bool {
	return t.readerLock.HasQueuedThreads()
}

// AcquireWriter override Tunnel.AcquireWriter
func (t *BaseTunnel) AcquireWriter() Writer {
	t.writerLock.Lock()
	return t.core.GetSocket().GetWriter()
}

// ReleaseWriter override Tunnel.ReleaseWriter
func (t *BaseTunnel) ReleaseWriter() {
	t.writerLock.Unlock()
}

// HasQueuedWriterThreads override Tunnel.HasQueuedWriterThreads
func (t *BaseTunnel) HasQueuedWriterThreads() bool {
	return t.writerLock.HasQueuedThreads()
}

// Close override Tunnel.Close
func (t *BaseTunnel) Close() (err error) {
	one := t.core.GetSocket()

	if one != nil {
		err = one.Close()
	} else {
		err = ErrConnectionClosed.NewError("Closed")
	}
	return
}

// IsOpen override Tunnel.IsOpen
func (t *BaseTunnel) IsOpen() bool {
	one := t.core.GetSocket()
	if one != nil {
		return one.IsOpen()
	}
	return false
}
