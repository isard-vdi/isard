package guac

import (
	"fmt"
)

// Instruction instruction container
// * An abstract representation of a Guacamole instruction, as defined by the
// * Guacamole protocol.
type Instruction struct {
	Opcode       string
	Args         []string
	ProtocolForm string
}

// NewInstruction Construct function
func NewInstruction(opcode string, args ...string) *Instruction {
	return &Instruction{
		Opcode: opcode,
		Args:   args,
	}
}

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
