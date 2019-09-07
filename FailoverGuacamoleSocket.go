package guac

// Move FailoverGuacamoleSocket from protocol folder to here
// Avoid cross depends

import (
	"strconv"
)

// log instread of LoggerFactory

const (
	/*InstructionQueueLimit *
	 * The maximum number of characters of Guacamole instruction data to store
	 * within the instruction queue while searching for errors. Once this limit
	 * is exceeded, the connection is assumed to be successful.
	 */
	InstructionQueueLimit int = 2048
)

// FailoverGuacamoleSocket ==> GuacamoleSocket
//  * GuacamoleSocket which intercepts errors received early in the Guacamole
//  * session. Upstream errors which are intercepted early enough result in
//  * exceptions thrown immediately within the FailoverGuacamoleSocket's
//  * constructor, allowing a different socket to be substituted prior to
//  * fulfilling the connection.
type FailoverGuacamoleSocket struct {
	/**
	 * The wrapped socket being used.
	 */
	socket GuacamoleSocket

	/**
	 * Queue of all instructions read while this FailoverGuacamoleSocket was
	 * being constructed.
	 */
	instructionQueue []GuacamoleInstruction

	/**
	 * GuacamoleReader which reads instructions from the queue populated when
	 * the FailoverGuacamoleSocket was constructed. Once the queue has been
	 * emptied, reads are delegated directly to the reader of the wrapped
	 * socket.
	 */
	queuedReader GuacamoleReader
}

/**
* Parses the given "error" instruction, throwing an exception if the
* instruction represents an error from the upstream remote desktop.
*
* @param instruction
*     The "error" instruction to parse.
*
* @throws GuacamoleUpstreamException
*     If the "error" instruction represents an error from the upstream
*     remote desktop.
 */
func handleUpstreamErrors(instruction GuacamoleInstruction) (err ExceptionInterface) {
	// Ignore error instructions which are missing the status code
	args := instruction.GetArgs()
	if len(args) < 2 {
		// logger.debug("Received \"error\" instruction without status code.");
		return
	}

	// Parse the status code from the received error instruction
	var statusCode int
	statusCode, e := strconv.Atoi(args[1])
	if e != nil {
		// logger.debug("Received \"error\" instruction with non-numeric status code.", e);
		return
	}

	status := FromGuacamoleStatusCode(statusCode)
	if status == Undifined {
		// logger.debug("Received \"error\" instruction with unknown/invalid status code: {}", statusCode);
		return
	}

	switch status {
	case UPSTREAM_ERROR:
		err = GuacamoleUpstreamException.Throw(args[0])

	case UPSTREAM_NOT_FOUND:
		err = GuacamoleUpstreamNotFoundException.Throw(args[0])

	// Upstream did not respond
	case UPSTREAM_TIMEOUT:
		err = GuacamoleUpstreamTimeoutException.Throw(args[0])

	// Upstream is refusing the connection
	case UPSTREAM_UNAVAILABLE:
		err = GuacamoleUpstreamUnavailableException.Throw(args[0])
	}
	return
}

/*NewFailoverGuacamoleSocket *
* Creates a new FailoverGuacamoleSocket which reads Guacamole instructions
* from the given socket, searching for errors from the upstream remote
* desktop. If an upstream error is encountered, it is thrown as a
* GuacamoleUpstreamException. This constructor will block until an error
* is encountered, or until the connection appears to have been successful.
* Once the FailoverGuacamoleSocket has been created, all reads, writes,
* etc. will be delegated to the provided socket.
*
* @param socket
*     The GuacamoleSocket of the Guacamole connection this
*     FailoverGuacamoleSocket should handle.
*
* @throws GuacamoleException
*     If an error occurs while reading data from the provided socket.
*
* @throws GuacamoleUpstreamException
*     If the connection to guacd succeeded, but an error occurred while
*     connecting to the remote desktop.
 */
func NewFailoverGuacamoleSocket(socket GuacamoleSocket) (ret FailoverGuacamoleSocket, err ExceptionInterface) {
	ret.instructionQueue = make([]GuacamoleInstruction, 0, 1)

	var totalQueueSize int

	var instruction GuacamoleInstruction
	reader := ret.socket.GetReader()

	// Continuously read instructions, searching for errors
	for instruction, err = reader.ReadInstruction(); len(instruction.GetOpcode()) > 0 && err == nil; instruction, err = reader.ReadInstruction() {
		// Add instruction to tail of instruction queue
		ret.instructionQueue = append(ret.instructionQueue, instruction)

		// If instruction is a "sync" instruction, stop reading
		opcode := instruction.GetOpcode()
		if opcode == "sync" {
			break
		}

		// If instruction is an "error" instruction, parse its contents and
		// stop reading
		if opcode == "error" {
			err = handleUpstreamErrors(instruction)
			return
		}

		// Otherwise, track total data parsed, and assume connection is
		// successful if no error encountered within reasonable space
		totalQueueSize += len(instruction.String())
		if totalQueueSize >= InstructionQueueLimit {
			break
		}
	}

	if err != nil {
		return
	}

	ret.socket = socket

	/**
	 * GuacamoleReader which reads instructions from the queue populated when
	 * the FailoverGuacamoleSocket was constructed. Once the queue has been
	 * emptied, reads are delegated directly to the reader of the wrapped
	 * socket.
	 */
	ret.queuedReader = newLambdaQueuedReader(&ret)
	return
}

// GetReader override GuacamoleSocket.GetReader
func (opt *FailoverGuacamoleSocket) GetReader() GuacamoleReader {
	return opt.queuedReader
}

// GetWriter override GuacamoleSocket.GetWriter
func (opt *FailoverGuacamoleSocket) GetWriter() GuacamoleWriter {
	return opt.socket.GetWriter()
}

// Close override GuacamoleSocket.Close
func (opt *FailoverGuacamoleSocket) Close() (err ExceptionInterface) {
	err = opt.socket.Close()
	return
}

// IsOpen override GuacamoleSocket.IsOpen
func (opt *FailoverGuacamoleSocket) IsOpen() bool {
	return opt.socket.IsOpen()
}

///////////////////////////////////////////////////////////////////
// ADD for lambda Interface
///////////////////////////////////////////////////////////////////

type lambdaQueuedReader struct {
	core *FailoverGuacamoleSocket
}

func newLambdaQueuedReader(core *FailoverGuacamoleSocket) (ret GuacamoleReader) {
	one := lambdaQueuedReader{}
	one.core = core
	ret = &one
	return
}

// Available override GuacamoleReader.Available
func (opt *lambdaQueuedReader) Available() (ok bool, err ExceptionInterface) {
	ok = len(opt.core.instructionQueue) > 0
	if ok {
		return
	}
	return opt.core.GetReader().Available()
}

// Read override GuacamoleReader.Read
func (opt *lambdaQueuedReader) Read() (ret []byte, err ExceptionInterface) {

	// Read instructions from queue before finally delegating to
	// underlying reader (received when FailoverGuacamoleSocket was
	// being constructed)
	if len(opt.core.instructionQueue) > 0 {
		instruction := opt.core.instructionQueue[0]
		opt.core.instructionQueue = opt.core.instructionQueue[1:]
		ret = []byte(instruction.String())
		return
	}

	return opt.core.socket.GetReader().Read()
}

// ReadInstruction override GuacamoleSocket.ReadInstruction
func (opt *lambdaQueuedReader) ReadInstruction() (ret GuacamoleInstruction,
	err ExceptionInterface) {

	// Read instructions from queue before finally delegating to
	// underlying reader (received when FailoverGuacamoleSocket was
	// being constructed)
	if len(opt.core.instructionQueue) > 0 {
		ret = opt.core.instructionQueue[0]
		opt.core.instructionQueue = opt.core.instructionQueue[1:]
		return
	}
	return opt.core.GetReader().ReadInstruction()
}
