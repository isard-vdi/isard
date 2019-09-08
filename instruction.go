package guac

import (
	"fmt"
)

// Instruction instruction container
// * An abstract representation of a Guacamole instruction, as defined by the
// * Guacamole protocol.
type Instruction struct {
	opcode       string
	args         []string
	protocolForm string
}

// NewInstruction Construct function
func NewInstruction(opcode string, args ...string) (ret Instruction) {
	ret.opcode = opcode
	ret.args = args
	return
}

// GetOpcode Returns the opcode associated with this Instruction.
// * @return The opcode associated with this Instruction.
func (opt *Instruction) GetOpcode() string {
	return opt.opcode
}

// GetArgs *
// * Returns a List of all argument values specified for this
// * Instruction. Note that the List returned is immutable.
// * Attempts to modify the list will result in exceptions.
// *
// * @return A List of all argument values specified for this
// *         Instruction.
func (opt *Instruction) GetArgs() []string {
	return opt.args
}

func (opt *Instruction) String() string {
	if len(opt.protocolForm) > 0 {
		return opt.protocolForm
	}

	opt.protocolForm = fmt.Sprintf("%d.%s", len(opt.opcode), opt.opcode)
	for _, value := range opt.args {
		opt.protocolForm += fmt.Sprintf(",%d.%s", len(value), value)
	}
	opt.protocolForm += ";"

	return opt.protocolForm
}
