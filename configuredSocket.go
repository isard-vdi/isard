package guac

// Move FailoverSocket from protocol folder to here
// Avoid cross depends

import (
	"fmt"
	"io"
)

// ConfiguredSocket ==> Socket
type ConfiguredSocket struct {
	Socket
	config *Config
	id     string
}

/*expect *
* Waits for the instruction having the given Opcode, returning that
* instruction once it has been read. If the instruction is never read,
* an exception is thrown.
*
* @param reader The reader to read instructions from.
* @param Opcode The Opcode of the instruction we are expecting.
* @return The instruction having the given Opcode.
* @throws ErrOther If an error occurs while reading, or if
*                            the expected instruction is not read.
 */
func (opt *ConfiguredSocket) expect(reader Reader, opcode string) (instruction Instruction, err error) {

	// Wait for an instruction
	instruction, err = reader.ReadInstruction()
	if err != nil {
		return
	}

	if len(instruction.Opcode) == 0 {
		err = ErrServer.NewError("End of stream while waiting for \"" + opcode + "\".")
		return
	}

	// Ensure instruction has expected Opcode
	if instruction.Opcode != opcode {
		err = ErrServer.NewError("Expected \"" + opcode + "\" instruction but instead received \"" + instruction.Opcode + "\".")
		return
	}
	return
}

/*NewConfiguredGuacamoleSocket2 *
* Creates a new ConfiguredSocket which uses the given
* Config to complete the initial protocol handshake over
* the given Socket. A default ClientInfo object
* is used to provide basic client information.
 */
func NewConfiguredGuacamoleSocket2(socket Socket, config *Config) (ConfiguredSocket, error) {
	return NewConfiguredSocket3(socket, config, NewGuacamoleClientInformation())
}

/*NewConfiguredSocket3 *
* Creates a new ConfiguredSocket which uses the given
* Config and ClientInfo to complete the
* initial protocol handshake over the given Socket.
 */
func NewConfiguredSocket3(socket Socket, config *Config, info *ClientInfo) (one ConfiguredSocket, err error) {
	one.Socket = socket
	one.config = config

	// Get reader and writer
	reader := socket.GetReader()
	writer := socket.GetWriter()

	// Get protocol / connection ID
	selectArg := config.ConnectionID
	if len(selectArg) == 0 {
		selectArg = config.Protocol
	}

	// Send requested protocol or connection ID
	_, err = WriteInstruction(writer, NewInstruction("select", selectArg))
	if err != nil {
		return
	}

	// Wait for server Args
	args, err := one.expect(reader, "args")
	if err != nil {
		return
	}

	// Build Args list off provided names and config
	argNameS := args.Args
	argValueS := make([]string, 0, len(argNameS))
	for _, argName := range argNameS {

		// Retrieve argument name

		// Get defined value for name
		value := config.Parameters[argName]

		// If value defined, set that value
		if len(value) == 0 {
			value = ""
		}
		argValueS = append(argValueS, value)
	}

	// Send size
	_, err = WriteInstruction(writer, NewInstruction("size",
		fmt.Sprintf("%v", info.OptimalScreenWidth),
		fmt.Sprintf("%v", info.OptimalScreenHeight),
		fmt.Sprintf("%v", info.OptimalResolution)),
	)

	if err != nil {
		return
	}

	// Send supported audio formats
	_, err = WriteInstruction(writer, NewInstruction("audio", info.AudioMimetypes...))
	if err != nil {
		return
	}

	// Send supported video formats
	_, err = WriteInstruction(writer, NewInstruction("video", info.VideoMimetypes...))
	if err != nil {
		return
	}

	// Send supported image formats
	_, err = WriteInstruction(writer, NewInstruction("image", info.ImageMimetypes...))
	if err != nil {
		return
	}

	// Send Args
	_, err = WriteInstruction(writer, NewInstruction("connect", argValueS...))
	if err != nil {
		return
	}

	// Wait for ready, store ID
	ready, err := one.expect(reader, "ready")
	if err != nil {
		return
	}

	readyArgs := ready.Args
	if len(readyArgs) == 0 {
		err = ErrServer.NewError("No connection ID received")
		return
	}

	one.id = readyArgs[0]

	return

}

func (opt *ConfiguredSocket) GetConnectionID() string {
	return opt.id
}

func WriteInstruction(writer io.Writer, instruction Instruction) (int, error) {
	return writer.Write([]byte(instruction.String()))
}
