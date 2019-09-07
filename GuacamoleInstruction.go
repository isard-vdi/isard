package guac

import (
	"fmt"
)

// GuacamoleInstruction instruction container
// * An abstract representation of a Guacamole instruction, as defined by the
// * Guacamole protocol.
type GuacamoleInstruction struct {
	opcode       string
	args         []string
	protocolForm string
}

// NewGuacamoleInstruction Construct function
func NewGuacamoleInstruction(opcode string, args ...string) (ret GuacamoleInstruction) {
	ret.opcode = opcode
	ret.args = args
	return
}

// GetOpcode Returns the opcode associated with this GuacamoleInstruction.
// * @return The opcode associated with this GuacamoleInstruction.
func (opt *GuacamoleInstruction) GetOpcode() string {
	return opt.opcode
}

// GetArgs *
// * Returns a List of all argument values specified for this
// * GuacamoleInstruction. Note that the List returned is immutable.
// * Attempts to modify the list will result in exceptions.
// *
// * @return A List of all argument values specified for this
// *         GuacamoleInstruction.
func (opt *GuacamoleInstruction) GetArgs() []string {
	return opt.args
}

func (opt *GuacamoleInstruction) String() string {
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
