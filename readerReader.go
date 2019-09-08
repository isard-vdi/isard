package guac

import (
	"fmt"
	"net"
	"strconv"
)

// readerReader A Reader which wraps a standard io Reader,
// using that Reader as the Guacamole instruction stream.
type readerReader struct {
	input      *Stream
	parseStart int
	buffer     []byte
	usedLength int
}

// NewReaderReader Construct function of readerReader
func NewReaderReader(input *Stream) (ret Reader) {
	one := readerReader{}
	one.input = input
	one.parseStart = 0
	one.buffer = make([]byte, 0, 20480)
	ret = &one
	return
}

// Available override Reader.Available
func (opt *readerReader) Available() (ok bool, err ExceptionInterface) {
	ok = len(opt.buffer) > 0
	if ok {
		return
	}
	ok, e := opt.input.Available()
	if e != nil {
		err = ServerException.Throw(e.Error())
		return
	}
	return
}

// Read override Reader.Read
func (opt *readerReader) Read() (instruction []byte, err ExceptionInterface) {

mainLoop:
	// While we're blocking, or input is available
	for {
		// Length of element
		var elementLength int

		// Resume where we left off
		i := opt.parseStart

	parseLoop:
		// Parse instruction in buffer
		for i < len(opt.buffer) {
			// Read character
			readChar := opt.buffer[i]
			i++

			switch readChar {
			// If digit, update length
			case '0', '1', '2', '3', '4', '5', '6', '7', '8', '9':
				elementLength = elementLength*10 + int(readChar-'0')

			// If not digit, check for end-of-length character
			case '.':
				if i+elementLength >= len(opt.buffer) {
					// break for i < opt.usedLength { ... }
					// Otherwise, read more data
					break parseLoop
				}
				// Check if element present in buffer
				terminator := opt.buffer[i+elementLength]
				// Move to character after terminator
				i += elementLength + 1

				// Reset length
				elementLength = 0

				// Continue here if necessary
				opt.parseStart = i

				// If terminator is semicolon, we have a full
				// instruction.
				switch terminator {
				case ';':
					instruction = opt.buffer[0:i]
					opt.parseStart = 0
					opt.buffer = opt.buffer[i:]
					break mainLoop
				case ',':
					// nothing
				default:
					err = ServerException.Throw("Element terminator of instruction was not ';' nor ','")
					break mainLoop
				}
			default:
				// Otherwise, parse error
				fmt.Println(string(opt.buffer))
				fmt.Println(string(opt.buffer[i]))
				err = ServerException.Throw("Non-numeric character in element length.")
				break mainLoop
			}

		}

		// no more buffer explain in golang
		// discard
		// if (usedLength > buffer.length/2) { ... }
		// using
		// Read(stepBuffer)
		// buffer = buffer + stepBuffer[0:n]
		// instead

		stepBuffer, e := opt.input.Read()
		if e != nil {
			// Discard
			// Time out throw GuacamoleUpstreamTimeoutException for
			// Closed throw GuacamoleConnectionClosedException for
			// Other socket err
			// Here or use normal err instead

			// Inside opt.input.Read()
			// Error occurs will close socket
			// So ...
			switch e.(type) {
			case net.Error:
				ex := e.(net.Error)
				if ex.Timeout() {
					err = GuacamoleUpstreamTimeoutException.Throw("Connection to guacd timed out.", e.Error())
				} else {
					err = GuacamoleConnectionClosedException.Throw("Connection to guacd is closed.", e.Error())
				}
			default:
				err = ServerException.Throw(e.Error())
			}
			break mainLoop
		}
		opt.buffer = append(opt.buffer, stepBuffer...)
	}
	return
}

// ReadInstruction override Reader.ReadInstruction
func (opt *readerReader) ReadInstruction() (instruction Instruction, err ExceptionInterface) {

	// Get instruction
	instructionBuffer, err := opt.Read()

	// If EOF, return EOF
	if err != nil {
		return
	}

	// Start of element
	elementStart := 0

	// Build list of elements
	elements := make([]string, 0, 1)
	for elementStart < len(instructionBuffer) {
		// Find end of length
		lengthEnd := -1
		for i := elementStart; i < len(instructionBuffer); i++ {
			if instructionBuffer[i] == '.' {
				lengthEnd = i
				break
			}
		}
		// read() is required to return a complete instruction. If it does
		// not, this is a severe internal error.
		if lengthEnd == -1 {
			err = ServerException.Throw("Read returned incomplete instruction.")
			return
		}

		// Parse length
		length, e := strconv.Atoi(string(instructionBuffer[elementStart:lengthEnd]))
		if e != nil {
			err = ServerException.Throw("Read returned wrong pattern instruction.", e.Error())
			return
		}

		// Parse element from just after period
		elementStart = lengthEnd + 1
		element := string(instructionBuffer[elementStart : elementStart+length])

		// Append element to list of elements
		elements = append(elements, element)

		// Read terminator after element
		elementStart += length
		terminator := instructionBuffer[elementStart]

		// Continue reading instructions after terminator
		elementStart++

		// If we've reached the end of the instruction
		if terminator == ';' {
			break
		}

	}

	// Pull opcode off elements list
	// Create instruction
	instruction = NewInstruction(elements[0], elements[1:]...)

	// Return parsed instruction
	return
}
