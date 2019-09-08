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

// NewAbstractTunnel Construct function
func NewAbstractTunnel(core GetSocketInterface) (ret BaseTunnel) {
	ret.core = core
	return
}

// AcquireReader override Tunnel.AcquireReader
func (opt *BaseTunnel) AcquireReader() Reader {
	opt.readerLock.Lock()
	return opt.core.GetSocket().GetReader()
}

// ReleaseReader override Tunnel.ReleaseReader
func (opt *BaseTunnel) ReleaseReader() {
	opt.readerLock.Unlock()
}

// HasQueuedReaderThreads override Tunnel.HasQueuedReaderThreads
func (opt *BaseTunnel) HasQueuedReaderThreads() bool {
	return opt.readerLock.HasQueuedThreads()
}

// AcquireWriter override Tunnel.AcquireWriter
func (opt *BaseTunnel) AcquireWriter() Writer {
	opt.writerLock.Lock()
	return opt.core.GetSocket().GetWriter()
}

// ReleaseWriter override Tunnel.ReleaseWriter
func (opt *BaseTunnel) ReleaseWriter() {
	opt.writerLock.Unlock()
}

// HasQueuedWriterThreads override Tunnel.HasQueuedWriterThreads
func (opt *BaseTunnel) HasQueuedWriterThreads() bool {
	return opt.writerLock.HasQueuedThreads()
}

// Close override Tunnel.Close
func (opt *BaseTunnel) Close() (err ExceptionInterface) {
	one := opt.core.GetSocket()

	if one != nil {
		err = one.Close()
	} else {
		err = GuacamoleConnectionClosedException.Throw("Closed")
	}
	return
}

// IsOpen override Tunnel.IsOpen
func (opt *BaseTunnel) IsOpen() bool {
	one := opt.core.GetSocket()
	if one != nil {
		return one.IsOpen()
	}
	return false
}
