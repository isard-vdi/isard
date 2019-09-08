package guac

import uuid "github.com/satori/go.uuid"

//InternalDataOpcode const Global value
//  * The Guacamole protocol instruction opcode reserved for arbitrary
//  * internal use by tunnel implementations. The value of this opcode is
//  * guaranteed to be the empty string (""). Tunnel implementations may use
//  * this opcode for any purpose. It is currently used by the HTTP tunnel to
//  * mark the end of the HTTP response, and by the WebSocket tunnel to
//  * transmit the tunnel UUID.
const InternalDataOpcode = ""

// Tunnel Provides a unique identifier and synchronized access
// to the Reader and Writer associated with a Socket.
type Tunnel interface {

	/**
	 * Acquires exclusive read access to the Guacamole instruction stream
	 * and returns a Reader for reading from that stream.
	 *
	 * @return A Reader for reading from the Guacamole instruction
	 *         stream.
	 */
	AcquireReader() Reader

	/**
	 * Relinquishes exclusive read access to the Guacamole instruction
	 * stream. This function should be called whenever a thread finishes using
	 * a Tunnel's Reader.
	 */
	ReleaseReader()

	/**
	 * Returns whether there are threads waiting for read access to the
	 * Guacamole instruction stream.
	 *
	 * @return true if threads are waiting for read access the Guacamole
	 *         instruction stream, false otherwise.
	 */
	HasQueuedReaderThreads() bool

	/**
	 * Acquires exclusive write access to the Guacamole instruction stream
	 * and returns a Writer for writing to that stream.
	 *
	 * @return A Writer for writing to the Guacamole instruction
	 *         stream.
	 */
	AcquireWriter() Writer

	/**
	 * Relinquishes exclusive write access to the Guacamole instruction
	 * stream. This function should be called whenever a thread finishes using
	 * a Tunnel's Writer.
	 */
	ReleaseWriter()

	/**
	 * Returns whether there are threads waiting for write access to the
	 * Guacamole instruction stream.
	 *
	 * @return true if threads are waiting for write access the Guacamole
	 *         instruction stream, false otherwise.
	 */
	HasQueuedWriterThreads() bool

	/**
	 * Returns the unique identifier associated with this Tunnel.
	 *
	 * @return The unique identifier associated with this Tunnel.
	 */
	GetUUID() uuid.UUID

	/**
	 * Returns the Socket used by this Tunnel for reading
	 * and writing.
	 *
	 * @return The Socket used by this Tunnel.
	 */
	GetSocket() Socket

	/**
	 * Release all resources allocated to this Tunnel.
	 *
	 * @throws GuacamoleException if an error occurs while releasing
	 *                            resources.
	 */
	Close() ExceptionInterface

	/**
	 * Returns whether this Tunnel is open, or has been closed.
	 *
	 * @return true if this Tunnel is open, false if it is closed.
	 */
	IsOpen() bool
}
