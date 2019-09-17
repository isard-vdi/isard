package guac

import (
	"fmt"
	"strconv"
)

// Instruction represents a Guacamole instruction
type Instruction struct {
	Opcode       string
	Args         []string
	ProtocolForm string
}

// NewInstruction creates an instruction
func NewInstruction(opcode string, args ...string) *Instruction {
	return &Instruction{
		Opcode: opcode,
		Args:   args,
	}
}

// String returns the on-wire representation of the instruction
func (opt *Instruction) String() string {
	if len(opt.ProtocolForm) > 0 {
		return opt.ProtocolForm
	}

	opt.ProtocolForm = fmt.Sprintf("%d.%s", len(opt.Opcode), opt.Opcode)
	for _, value := range opt.Args {
		opt.ProtocolForm += fmt.Sprintf(",%d.%s", len(value), value)
	}
	opt.ProtocolForm += ";"

	return opt.ProtocolForm
}

// ReadOne takes an instruction from the stream and parses it into an Instruction
func ReadOne(stream *Stream) (instruction *Instruction, err error) {
	var instructionBuffer []byte

	// Get instruction
	instructionBuffer, err = stream.ReadSome()

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
