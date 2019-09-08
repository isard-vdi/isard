package guac

// FilteredSocket ==> Socket
// * Implementation of Socket which allows individual instructions to be
// * intercepted, overridden, etc.
type FilteredSocket struct {
	/**
	 * Wrapped Socket.
	 */
	socket Socket

	/**
	 * A reader for the wrapped Socket which may be filtered.
	 */
	reader Reader

	/**
	 * A writer for the wrapped Socket which may be filtered.
	 */
	writer Writer
}

/*NewFilteredSocket *
* Creates a new FilteredSocket which uses the given filters to
* determine whether instructions read/written are allowed through,
* modified, etc. If reads or writes should be unfiltered, simply specify
* null rather than a particular filter.
*
* @param socket The Socket to wrap.
* @param readFilter The Filter to apply to all read instructions,
*                   if any.
* @param writeFilter The Filter to apply to all written
*                    instructions, if any.
 */
func NewFilteredSocket(socket Socket, readFilter Filter, writeFilter Filter) *FilteredSocket {
	filteredSock := &FilteredSocket{
		socket: socket,
	}

	// Apply filter to reader
	if readFilter != nil {
		reader := NewFilteredReader(socket.GetReader(), readFilter)
		filteredSock.reader = reader
	} else {
		filteredSock.reader = socket.GetReader()
	}

	// Apply filter to writer
	if writeFilter != nil {
		writer := NewFilteredWriter(socket.GetWriter(), writeFilter)
		filteredSock.writer = &writer
	} else {
		filteredSock.writer = socket.GetWriter()
	}

	return filteredSock
}

// GetReader override Socket.GetReader
func (opt *FilteredSocket) GetReader() Reader {
	return opt.reader
}

// GetWriter override Socket.GetWriter
func (opt *FilteredSocket) GetWriter() Writer {
	return opt.writer
}

// Close override Socket.Close
func (opt *FilteredSocket) Close() ExceptionInterface {
	return opt.socket.Close()

}

// IsOpen override Socket.IsOpen
func (opt *FilteredSocket) IsOpen() bool {
	return opt.socket.IsOpen()
}
