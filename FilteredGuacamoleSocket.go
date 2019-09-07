package guac

// Move FilteredGuacamoleSocket from protocol folder to here
// Avoid cross depends

// FilteredGuacamoleSocket ==> GuacamoleSocket
// * Implementation of GuacamoleSocket which allows individual instructions to be
// * intercepted, overridden, etc.
type FilteredGuacamoleSocket struct {
	/**
	 * Wrapped GuacamoleSocket.
	 */
	socket GuacamoleSocket

	/**
	 * A reader for the wrapped GuacamoleSocket which may be filtered.
	 */
	reader GuacamoleReader

	/**
	 * A writer for the wrapped GuacamoleSocket which may be filtered.
	 */
	writer GuacamoleWriter
}

/*NewFilteredGuacamoleSocket *
* Creates a new FilteredGuacamoleSocket which uses the given filters to
* determine whether instructions read/written are allowed through,
* modified, etc. If reads or writes should be unfiltered, simply specify
* null rather than a particular filter.
*
* @param socket The GuacamoleSocket to wrap.
* @param readFilter The GuacamoleFilter to apply to all read instructions,
*                   if any.
* @param writeFilter The GuacamoleFilter to apply to all written
*                    instructions, if any.
 */
func NewFilteredGuacamoleSocket(
	socket GuacamoleSocket,
	readFilter GuacamoleFilter,
	writeFilter GuacamoleFilter,
) (ret FilteredGuacamoleSocket) {

	ret.socket = socket

	// Apply filter to reader
	if readFilter != nil {
		reader := NewFilteredGuacamoleReader(socket.GetReader(), readFilter)
		ret.reader = &reader
	} else {
		ret.reader = socket.GetReader()
	}

	// Apply filter to writer
	if writeFilter != nil {
		writer := NewFilteredGuacamoleWriter(socket.GetWriter(), writeFilter)
		ret.writer = &writer
	} else {
		ret.writer = socket.GetWriter()
	}

	return
}

// GetReader override GuacamoleSocket.GetReader
func (opt *FilteredGuacamoleSocket) GetReader() GuacamoleReader {
	return opt.reader
}

// GetWriter override GuacamoleSocket.GetWriter
func (opt *FilteredGuacamoleSocket) GetWriter() GuacamoleWriter {
	return opt.writer
}

// Close override GuacamoleSocket.Close
func (opt *FilteredGuacamoleSocket) Close() ExceptionInterface {
	return opt.socket.Close()

}

// IsOpen override GuacamoleSocket.IsOpen
func (opt *FilteredGuacamoleSocket) IsOpen() bool {
	return opt.socket.IsOpen()
}
