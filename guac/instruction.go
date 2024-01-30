package guac

import (
	"fmt"
	"strconv"
)

// Instruction represents a Guacamole instruction
type Instruction struct {
	Opcode string
	Args   []string
	cache  string
}

// NewInstruction creates an instruction
func NewInstruction(opcode string, args ...string) *Instruction {
	return &Instruction{
		Opcode: opcode,
		Args:   args,
	}
}

// String returns the on-wire representation of the instruction
func (i *Instruction) String() string {
	if len(i.cache) > 0 {
		return i.cache
	}

	i.cache = fmt.Sprintf("%d.%s", len(i.Opcode), i.Opcode)
	for _, value := range i.Args {
		i.cache += fmt.Sprintf(",%d.%s", len(value), value)
	}
	i.cache += ";"

	return i.cache
}

func (i *Instruction) Byte() []byte {
	return []byte(i.String())
}

func Parse(data []byte) (*Instruction, error) {
	elementStart := 0

	// Build list of elements
	elements := make([]string, 0, 1)
	for elementStart < len(data) {
		// Find end of length
		lengthEnd := -1
		for i := elementStart; i < len(data); i++ {
			if data[i] == '.' {
				lengthEnd = i
				break
			}
		}
		// read() is required to return a complete instruction. If it does
		// not, this is a severe internal error.
		if lengthEnd == -1 {
			return nil, ErrServer.NewError("ReadSome returned incomplete instruction.")
		}

		// Parse length
		length, e := strconv.Atoi(string(data[elementStart:lengthEnd]))
		if e != nil {
			return nil, ErrServer.NewError("ReadSome returned wrong pattern instruction.", e.Error())
		}

		// Parse element from just after period
		elementStart = lengthEnd + 1
		element := string(data[elementStart : elementStart+length])

		// Append element to list of elements
		elements = append(elements, element)

		// ReadSome terminator after element
		elementStart += length
		terminator := data[elementStart]

		// Continue reading instructions after terminator
		elementStart++

		// If we've reached the end of the instruction
		if terminator == ';' {
			break
		}

	}

	return NewInstruction(elements[0], elements[1:]...), nil
}

// ReadOne takes an instruction from the stream and parses it into an Instruction
func ReadOne(stream *Stream) (instruction *Instruction, err error) {
	var instructionBuffer []byte
	instructionBuffer, err = stream.ReadSome()
	if err != nil {
		return
	}

	return Parse(instructionBuffer)
}
