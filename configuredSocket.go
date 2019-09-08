package guac

// Move FailoverSocket from protocol folder to here
// Avoid cross depends

import (
	"fmt"
)

// ConfiguredSocket ==> Socket
type ConfiguredSocket struct {

	/**
	 * The wrapped socket.
	 */
	socket Socket

	/**
	 * The configuration to use when performing the Guacamole protocol
	 * handshake.
	 */
	config Config

	/**
	 * The unique identifier associated with this connection, as determined
	 * by the "ready" instruction received from the Guacamole proxy.
	 */
	id string
}

/*expect *
* Waits for the instruction having the given opcode, returning that
* instruction once it has been read. If the instruction is never read,
* an exception is thrown.
*
* @param reader The reader to read instructions from.
* @param opcode The opcode of the instruction we are expecting.
* @return The instruction having the given opcode.
* @throws ErrOther If an error occurs while reading, or if
*                            the expected instruction is not read.
 */
func (opt *ConfiguredSocket) expect(reader Reader, opcode string) (instruction Instruction, err error) {

	// Wait for an instruction
	instruction, err = reader.ReadInstruction()
	if err != nil {
		return
	}

	if len(instruction.GetOpcode()) == 0 {
		err = ErrServer.NewError("End of stream while waiting for \"" + opcode + "\".")
		return
	}

	// Ensure instruction has expected opcode
	if instruction.GetOpcode() != opcode {
		err = ErrServer.NewError("Expected \"" + opcode + "\" instruction but instead received \"" + instruction.GetOpcode() + "\".")
		return
	}
	return
}

/*NewConfiguredGuacamoleSocket2 *
* Creates a new ConfiguredSocket which uses the given
* Config to complete the initial protocol handshake over
* the given Socket. A default ClientInfo object
* is used to provide basic client information.
*
* @param socket The Socket to wrap.
* @param config The Config to use to complete the initial
*               protocol handshake.
* @throws ErrOther If an error occurs while completing the
*                            initial protocol handshake.
 */
func NewConfiguredGuacamoleSocket2(socket Socket, config Config) (ConfiguredSocket, error) {
	return NewConfiguredSocket3(socket, config, NewGuacamoleClientInformation())
}

/*NewConfiguredSocket3 *
* Creates a new ConfiguredSocket which uses the given
* Config and ClientInfo to complete the
* initial protocol handshake over the given Socket.
*
* @param socket The Socket to wrap.
* @param config The Config to use to complete the initial
*               protocol handshake.
* @param info The ClientInfo to use to complete the initial
*             protocol handshake.
* @throws ErrOther If an error occurs while completing the
*                            initial protocol handshake.
 */
func NewConfiguredSocket3(socket Socket, config Config, info ClientInfo) (one ConfiguredSocket, err error) {

	one.socket = socket
	one.config = config

	// Get reader and writer
	reader := socket.GetReader()
	writer := socket.GetWriter()

	// Get protocol / connection ID
	selectArg := config.GetConnectionID()
	if len(selectArg) == 0 {
		selectArg = config.GetProtocol()
	}

	// Send requested protocol or connection ID
	err = writer.WriteInstruction(NewInstruction("select", selectArg))
	if err != nil {
		return
	}

	// Wait for server args
	args, err := one.expect(reader, "args")
	if err != nil {
		return
	}

	// Build args list off provided names and config
	argNameS := args.GetArgs()
	argValueS := make([]string, 0, len(argNameS))
	for _, argName := range argNameS {

		// Retrieve argument name

		// Get defined value for name
		value := config.GetParameter(argName)

		// If value defined, set that value
		if len(value) == 0 {
			value = ""
		}
		argValueS = append(argValueS, value)
	}

	// Send size
	err = writer.WriteInstruction(NewInstruction("size",
		fmt.Sprintf("%v", info.GetOptimalScreenWidth()),
		fmt.Sprintf("%v", info.GetOptimalScreenHeight()),
		fmt.Sprintf("%v", info.GetOptimalResolution())),
	)

	if err != nil {
		return
	}

	// Send supported audio formats
	err = writer.WriteInstruction(
		NewInstruction(
			"audio",
			info.GetAudioMimetypes()...,
		))
	if err != nil {
		return
	}

	// Send supported video formats
	err = writer.WriteInstruction(
		NewInstruction(
			"video",
			info.GetVideoMimetypes()...,
		))
	if err != nil {
		return
	}

	// Send supported image formats
	err = writer.WriteInstruction(
		NewInstruction(
			"image",
			info.GetImageMimetypes()...,
		))
	if err != nil {
		return
	}

	// Send args
	err = writer.WriteInstruction(NewInstruction("connect", argValueS...))
	if err != nil {
		return
	}

	// Wait for ready, store ID
	ready, err := one.expect(reader, "ready")
	if err != nil {
		return
	}

	readyArgs := ready.GetArgs()
	if len(readyArgs) == 0 {
		err = ErrServer.NewError("No connection ID received")
		return
	}

	one.id = readyArgs[0]

	return

}

/*GetConfiguration *
* Returns the Config used to configure this
* ConfiguredSocket.
*
* @return The Config used to configure this
*         ConfiguredSocket.
 */
func (opt *ConfiguredSocket) GetConfiguration() Config {
	return opt.config
}

/*GetConnectionID *
* Returns the unique ID associated with the Guacamole connection
* negotiated by this ConfiguredSocket. The ID is provided by
* the "ready" instruction returned by the Guacamole proxy.
*
* @return The ID of the negotiated Guacamole connection.
 */
func (opt *ConfiguredSocket) GetConnectionID() string {
	return opt.id
}

// GetWriter override Socket.GetWriter
func (opt *ConfiguredSocket) GetWriter() Writer {
	return opt.socket.GetWriter()
}

// GetReader override Socket.GetReader
func (opt *ConfiguredSocket) GetReader() Reader {
	return opt.socket.GetReader()
}

// Close override Socket.Close
func (opt *ConfiguredSocket) Close() (err error) {
	return opt.socket.Close()
}

// IsOpen override Socket.IsOpen
func (opt *ConfiguredSocket) IsOpen() bool {
	return opt.socket.IsOpen()
}
