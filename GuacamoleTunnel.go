package guac

import uuid "github.com/satori/go.uuid"

//InternalDataOpcode const Globle value
//  * The Guacamole protocol instruction opcode reserved for arbitrary
//  * internal use by tunnel implementations. The value of this opcode is
//  * guaranteed to be the empty string (""). Tunnel implementations may use
//  * this opcode for any purpose. It is currently used by the HTTP tunnel to
//  * mark the end of the HTTP response, and by the WebSocket tunnel to
//  * transmit the tunnel UUID.
const InternalDataOpcode = ""

// GuacamoleTunnel Provides a unique identifier and synchronized access
// to the GuacamoleReader and GuacamoleWriter associated with a GuacamoleSocket.
type GuacamoleTunnel interface {

	/**
	 * Acquires exclusive read access to the Guacamole instruction stream
	 * and returns a GuacamoleReader for reading from that stream.
	 *
	 * @return A GuacamoleReader for reading from the Guacamole instruction
	 *         stream.
	 */
	AcquireReader() GuacamoleReader

	/**
	 * Relinquishes exclusive read access to the Guacamole instruction
	 * stream. This function should be called whenever a thread finishes using
	 * a GuacamoleTunnel's GuacamoleReader.
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
	 * and returns a GuacamoleWriter for writing to that stream.
	 *
	 * @return A GuacamoleWriter for writing to the Guacamole instruction
	 *         stream.
	 */
	AcquireWriter() GuacamoleWriter

	/**
	 * Relinquishes exclusive write access to the Guacamole instruction
	 * stream. This function should be called whenever a thread finishes using
	 * a GuacamoleTunnel's GuacamoleWriter.
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
	 * Returns the unique identifier associated with this GuacamoleTunnel.
	 *
	 * @return The unique identifier associated with this GuacamoleTunnel.
	 */
	GetUUID() uuid.UUID

	/**
	 * Returns the GuacamoleSocket used by this GuacamoleTunnel for reading
	 * and writing.
	 *
	 * @return The GuacamoleSocket used by this GuacamoleTunnel.
	 */
	GetSocket() GuacamoleSocket

	/**
	 * Release all resources allocated to this GuacamoleTunnel.
	 *
	 * @throws GuacamoleException if an error occurs while releasing
	 *                            resources.
	 */
	Close() ExceptionInterface

	/**
	 * Returns whether this GuacamoleTunnel is open, or has been closed.
	 *
	 * @return true if this GuacamoleTunnel is open, false if it is closed.
	 */
	IsOpen() bool
}
