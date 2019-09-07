package guac

// AbstractGuacamoleTunnel ==> GuacamoleTunnel
//  * Base GuacamoleTunnel implementation which synchronizes access to the
//  * underlying reader and writer with reentrant locks. Implementations need only
//  * provide the tunnel's UUID and socket.
type AbstractGuacamoleTunnel struct {
	core       GetSocketInterface
	readerLock ReentrantLock
	writerLock ReentrantLock
}

// NewAbstractGuacamoleTunnel Construct function
func NewAbstractGuacamoleTunnel(core GetSocketInterface) (ret AbstractGuacamoleTunnel) {
	ret.core = core
	return
}

// AcquireReader override GuacamoleTunnel.AcquireReader
func (opt *AbstractGuacamoleTunnel) AcquireReader() GuacamoleReader {
	opt.readerLock.Lock()
	return opt.core.GetSocket().GetReader()
}

// ReleaseReader override GuacamoleTunnel.ReleaseReader
func (opt *AbstractGuacamoleTunnel) ReleaseReader() {
	opt.readerLock.Unlock()
}

// HasQueuedReaderThreads override GuacamoleTunnel.HasQueuedReaderThreads
func (opt *AbstractGuacamoleTunnel) HasQueuedReaderThreads() bool {
	return opt.readerLock.HasQueuedThreads()
}

// AcquireWriter override GuacamoleTunnel.AcquireWriter
func (opt *AbstractGuacamoleTunnel) AcquireWriter() GuacamoleWriter {
	opt.writerLock.Lock()
	return opt.core.GetSocket().GetWriter()
}

// ReleaseWriter override GuacamoleTunnel.ReleaseWriter
func (opt *AbstractGuacamoleTunnel) ReleaseWriter() {
	opt.writerLock.Unlock()
}

// HasQueuedWriterThreads override GuacamoleTunnel.HasQueuedWriterThreads
func (opt *AbstractGuacamoleTunnel) HasQueuedWriterThreads() bool {
	return opt.writerLock.HasQueuedThreads()
}

// Close override GuacamoleTunnel.Close
func (opt *AbstractGuacamoleTunnel) Close() (err ExceptionInterface) {
	one := opt.core.GetSocket()

	if one != nil {
		err = one.Close()
	} else {
		err = GuacamoleConnectionClosedException.Throw("Closed")
	}
	return
}

// IsOpen override GuacamoleTunnel.IsOpen
func (opt *AbstractGuacamoleTunnel) IsOpen() bool {
	one := opt.core.GetSocket()
	if one != nil {
		return one.IsOpen()
	}
	return false
}
