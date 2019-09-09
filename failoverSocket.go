package guac

import (
	"io"
	"strconv"
)

const (
	/*InstructionQueueLimit *
	 * The maximum number of characters of Guacamole instruction data to store
	 * within the instruction queue while searching for errors. Once this limit
	 * is exceeded, the connection is assumed to be successful.
	 */
	InstructionQueueLimit int = 2048
)

// FailoverSocket ==> Socket
//  * Socket which intercepts errors received early in the Guacamole
//  * session. Upstream errors which are intercepted early enough result in
//  * exceptions thrown immediately within the FailoverSocket's
//  * constructor, allowing a different socket to be substituted prior to
//  * fulfilling the connection.
type FailoverSocket struct {
	/**
	 * The wrapped socket being used.
	 */
	socket Socket

	/**
	 * Queue of all instructions read while this FailoverSocket was
	 * being constructed.
	 */
	instructionQueue []Instruction

	/**
	 * Reader which reads instructions from the queue populated when
	 * the FailoverSocket was constructed. Once the queue has been
	 * emptied, reads are delegated directly to the reader of the wrapped
	 * socket.
	 */
	queuedReader Reader
}

/**
* Parses the given "error" instruction, throwing an exception if the
* instruction represents an error from the upstream remote desktop.
*
* @param instruction
*     The "error" instruction to parse.
*
* @throws ErrUpstream
*     If the "error" instruction represents an error from the upstream
*     remote desktop.
 */
func handleUpstreamErrors(instruction Instruction) (err error) {
	// Ignore error instructions which are missing the Status code
	args := instruction.Args
	if len(args) < 2 {
		// logger.debug("Received \"error\" instruction without Status code.");
		return
	}

	// Parse the Status code from the received error instruction
	var statusCode int
	statusCode, e := strconv.Atoi(args[1])
	if e != nil {
		// logger.debug("Received \"error\" instruction with non-numeric Status code.", e);
		return
	}

	status := FromGuacamoleStatusCode(statusCode)
	if status == Undefined {
		// logger.debug("Received \"error\" instruction with unknown/invalid Status code: {}", statusCode);
		return
	}

	switch status {
	case UpstreamError:
		err = ErrUpstream.NewError(args[0])

	case UpstreamNotFound:
		err = ErrUpstreamNotFound.NewError(args[0])

	// Upstream did not respond
	case UpstreamTimeout:
		err = ErrUpstreamTimeout.NewError(args[0])

	// Upstream is refusing the connection
	case UpstreamUnavailable:
		err = ErrUpstreamUnavailable.NewError(args[0])
	}
	return
}

/*NewFailoverSocket *
* Creates a new FailoverSocket which reads Guacamole instructions
* from the given socket, searching for errors from the upstream remote
* desktop. If an upstream error is encountered, it is thrown as a
* ErrUpstream. This constructor will block until an error
* is encountered, or until the connection appears to have been successful.
* Once the FailoverSocket has been created, all reads, writes,
* etc. will be delegated to the provided socket.
*
* @param socket
*     The Socket of the Guacamole connection this
*     FailoverSocket should handle.
*
* @throws ErrOther
*     If an error occurs while reading data from the provided socket.
*
* @throws ErrUpstream
*     If the connection to guacd succeeded, but an error occurred while
*     connecting to the remote desktop.
 */
func NewFailoverSocket(socket Socket) (ret FailoverSocket, err error) {
	ret.instructionQueue = make([]Instruction, 0, 1)

	var totalQueueSize int

	var instruction Instruction
	reader := ret.socket.GetReader()

	// Continuously read instructions, searching for errors
	for instruction, err = reader.ReadInstruction(); len(instruction.Opcode) > 0 && err == nil; instruction, err = reader.ReadInstruction() {
		// Add instruction to tail of instruction queue
		ret.instructionQueue = append(ret.instructionQueue, instruction)

		// If instruction is a "sync" instruction, stop reading
		opcode := instruction.Opcode
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
	 * Reader which reads instructions from the queue populated when
	 * the FailoverSocket was constructed. Once the queue has been
	 * emptied, reads are delegated directly to the reader of the wrapped
	 * socket.
	 */
	ret.queuedReader = newLambdaQueuedReader(&ret)
	return
}

// GetReader override Socket.GetReader
func (opt *FailoverSocket) GetReader() Reader {
	return opt.queuedReader
}

// GetWriter override Socket.GetWriter
func (opt *FailoverSocket) GetWriter() io.Writer {
	return opt.socket.GetWriter()
}

// Close override Socket.Close
func (opt *FailoverSocket) Close() (err error) {
	err = opt.socket.Close()
	return
}

// IsOpen override Socket.IsOpen
func (opt *FailoverSocket) IsOpen() bool {
	return opt.socket.IsOpen()
}

/**
 * GuacamoleReader which reads instructions from the queue populated when
 * the FailoverGuacamoleSocket was constructed. Once the queue has been
 * emptied, reads are delegated directly to the reader of the wrapped
 * socket.
 */

type lambdaQueuedReader struct {
	core *FailoverSocket
}

func newLambdaQueuedReader(core *FailoverSocket) (ret Reader) {
	one := lambdaQueuedReader{}
	one.core = core
	ret = &one
	return
}

// Available override Reader.Available
func (opt *lambdaQueuedReader) Available() (ok bool, err error) {
	ok = len(opt.core.instructionQueue) > 0
	if ok {
		return
	}
	return opt.core.GetReader().Available()
}

// Read override Reader.Read
func (opt *lambdaQueuedReader) Read() (ret []byte, err error) {

	// Read instructions from queue before finally delegating to
	// underlying reader (received when FailoverSocket was
	// being constructed)
	if len(opt.core.instructionQueue) > 0 {
		instruction := opt.core.instructionQueue[0]
		opt.core.instructionQueue = opt.core.instructionQueue[1:]
		ret = []byte(instruction.String())
		return
	}

	return opt.core.socket.GetReader().Read()
}

// ReadInstruction override Socket.ReadInstruction
func (opt *lambdaQueuedReader) ReadInstruction() (ret Instruction,
	err error) {

	// Read instructions from queue before finally delegating to
	// underlying reader (received when FailoverSocket was
	// being constructed)
	if len(opt.core.instructionQueue) > 0 {
		ret = opt.core.instructionQueue[0]
		opt.core.instructionQueue = opt.core.instructionQueue[1:]
		return
	}
	return opt.core.GetReader().ReadInstruction()
}
