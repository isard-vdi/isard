package guac

import (
	"net"
	"strconv"
)

const maxGuacMessage = 8192

// InstructionReader A Reader which wraps a standard io Reader,
// using that Reader as the Guacamole instruction stream.
type InstructionReader struct {
	input      *Stream
	parseStart int
	buffer     []byte
	reset      []byte
}

// NewInstructionReader Construct function of InstructionReader
func NewInstructionReader(input *Stream) *InstructionReader {
	buffer := make([]byte, 0, maxGuacMessage*3)
	return &InstructionReader{
		input:      input,
		parseStart: 0,
		buffer:     buffer,
		reset:      buffer[:cap(buffer)],
	}
}

// Available override Reader.Available
func (r *InstructionReader) Available() bool {
	return len(r.buffer) > 0
}

func (r *InstructionReader) Flush() {
	copy(r.reset, r.buffer)
	r.buffer = r.reset[:len(r.buffer)]
}

// ReadSome override Reader.ReadSome
func (r *InstructionReader) ReadSome() (instruction []byte, err error) {
	var n int
	// While we're blocking, or input is available
	for {
		// Length of element
		var elementLength int

		// Resume where we left off
		i := r.parseStart

	parseLoop:
		// Parse instruction in buffer
		for i < len(r.buffer) {
			// ReadSome character
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
					return
				case ',':
					// keep going
				default:
					err = ErrServer.NewError("Element terminator of instruction was not ';' nor ','")
					return
				}
			default:
				// Otherwise, parse error
				err = ErrServer.NewError("Non-numeric character in element length:", string(readChar))
				return
			}
		}

		if cap(r.buffer) < maxGuacMessage {
			r.Flush()
		}

		n, err = r.input.Read(r.buffer[len(r.buffer):cap(r.buffer)])
		if err != nil {
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
			return
		}
		if n == 0 {
			err = ErrServer.NewError("read 0 bytes")
		}
		// must reslice so len is changed
		r.buffer = r.buffer[:len(r.buffer)+n]
	}
}

// ReadOne override Reader.ReadOne
func (r *InstructionReader) ReadOne() (instruction *Instruction, err error) {
	var instructionBuffer []byte

	// Get instruction
	instructionBuffer, err = r.ReadSome()

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
			err = ErrServer.NewError("ReadSome returned incomplete instruction.")
			return
		}

		// Parse length
		length, e := strconv.Atoi(string(instructionBuffer[elementStart:lengthEnd]))
		if e != nil {
			err = ErrServer.NewError("ReadSome returned wrong pattern instruction.", e.Error())
			return
		}

		// Parse element from just after period
		elementStart = lengthEnd + 1
		element := string(instructionBuffer[elementStart : elementStart+length])

		// Append element to list of elements
		elements = append(elements, element)

		// ReadSome terminator after element
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
