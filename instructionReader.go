package guac

import (
	"net"
	"strconv"
)

// instructionReader A Reader which wraps a standard io Reader,
// using that Reader as the Guacamole instruction stream.
type instructionReader struct {
	input      *Stream
	parseStart int
	buffer     []byte
	usedLength int
}

// NewInstructionReader Construct function of instructionReader
func NewInstructionReader(input *Stream) Reader {
	return &instructionReader{
		input:      input,
		parseStart: 0,
		buffer:     make([]byte, 0, 20480),
	}
}

// Available override Reader.Available
func (r *instructionReader) Available() (ok bool, err error) {
	ok = len(r.buffer) > 0
	if ok {
		return
	}
	ok, e := r.input.Available()
	if e != nil {
		err = ErrServer.NewError(e.Error())
		return
	}
	return
}

// Read override Reader.Read
func (r *instructionReader) Read() (instruction []byte, err error) {
	var n int
	stepBuffer := make([]byte, StepLength)

mainLoop:
	// While we're blocking, or input is available
	for {
		// Length of element
		var elementLength int

		// Resume where we left off
		i := r.parseStart

	parseLoop:
		// Parse instruction in buffer
		for i < len(r.buffer) {
			// Read character
			readChar := r.buffer[i]
			i++

			switch readChar {
			// If digit, update length
			case '0', '1', '2', '3', '4', '5', '6', '7', '8', '9':
				elementLength = elementLength*10 + int(readChar-'0')

			// If not digit, check for end-of-length character
			case '.':
				if i+elementLength >= len(r.buffer) {
					// break for i < r.usedLength { ... }
					// Otherwise, read more data
					break parseLoop
				}
				// Check if element present in buffer
				terminator := r.buffer[i+elementLength]
				// Move to character after terminator
				i += elementLength + 1

				// Reset length
				elementLength = 0

				// Continue here if necessary
				r.parseStart = i

				// If terminator is semicolon, we have a full
				// instruction.
				switch terminator {
				case ';':
					instruction = r.buffer[0:i]
					r.parseStart = 0
					r.buffer = r.buffer[i:]
					break mainLoop
				case ',':
					// nothing
				default:
					err = ErrServer.NewError("Element terminator of instruction was not ';' nor ','")
					break mainLoop
				}
			default:
				// Otherwise, parse error
				err = ErrServer.NewError("Non-numeric character in element length:", string(readChar))
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

		n, err = r.input.Read(stepBuffer)
		if err != nil {
			// Discard
			// Time out throw ErrUpstreamTimeout for
			// Closed throw ErrConnectionClosed for
			// Other socket err
			// Here or use normal err instead

			// Inside r.input.Read()
			// Error occurs will close socket
			// So ...
			switch err.(type) {
			case net.Error:
				ex := err.(net.Error)
				if ex.Timeout() {
					err = ErrUpstreamTimeout.NewError("Connection to guacd timed out.", err.Error())
				} else {
					err = ErrConnectionClosed.NewError("Connection to guacd is closed.", err.Error())
				}
			default:
				err = ErrServer.NewError(err.Error())
			}
			break mainLoop
		}
		r.buffer = append(r.buffer, stepBuffer[0:n]...)
	}
	return
}

// ReadInstruction override Reader.ReadInstruction
func (r *instructionReader) ReadInstruction() (instruction Instruction, err error) {
	var instructionBuffer []byte

	// Get instruction
	instructionBuffer, err = r.Read()

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
			err = ErrServer.NewError("Read returned incomplete instruction.")
			return
		}

		// Parse length
		length, e := strconv.Atoi(string(instructionBuffer[elementStart:lengthEnd]))
		if e != nil {
			err = ErrServer.NewError("Read returned wrong pattern instruction.", e.Error())
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

	// Pull Opcode off elements list
	// Create instruction
	instruction = NewInstruction(elements[0], elements[1:]...)

	// Return parsed instruction
	return
}
