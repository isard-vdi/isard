package guac

// Socket Provides abstract socket-like access to a Guacamole connection.
type Socket interface {
	/**
	 * Returns a Reader which can be used to read from the
	 * Guacamole instruction stream associated with the connection
	 * represented by this Socket.
	 *
	 * @return A Reader which can be used to read from the
	 *         Guacamole instruction stream.
	 */
	GetReader() Reader

	/**
	 * Returns a Writer which can be used to write to the
	 * Guacamole instruction stream associated with the connection
	 * represented by this Socket.
	 *
	 * @return A Writer which can be used to write to the
	 *         Guacamole instruction stream.
	 */
	GetWriter() Writer

	/**
	 * Releases all resources in use by the connection represented by this
	 * Socket.
	 *
	 * @throws ErrOther If an error occurs while releasing resources.
	 */
	Close() error

	/**
	 * Returns whether this Socket is open and can be used for reading
	 * and writing.
	 *
	 * @return true if this Socket is open, false otherwise.
	 */
	IsOpen() bool
}
