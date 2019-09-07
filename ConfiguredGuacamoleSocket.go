package guac

// Move FailoverGuacamoleSocket from protocol folder to here
// Avoid cross depends

import (
	"fmt"
)

// ConfiguredGuacamoleSocket ==> GuacamoleSocket
type ConfiguredGuacamoleSocket struct {

	/**
	 * The wrapped socket.
	 */
	socket GuacamoleSocket

	/**
	 * The configuration to use when performing the Guacamole protocol
	 * handshake.
	 */
	config GuacamoleConfiguration

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
* @throws GuacamoleException If an error occurs while reading, or if
*                            the expected instruction is not read.
 */
func (opt *ConfiguredGuacamoleSocket) expect(reader GuacamoleReader, opcode string) (instruction GuacamoleInstruction, err ExceptionInterface) {

	// Wait for an instruction
	instruction, err = reader.ReadInstruction()
	if err != nil {
		return
	}

	if len(instruction.GetOpcode()) == 0 {
		err = GuacamoleServerException.Throw("End of stream while waiting for \"" + opcode + "\".")
		return
	}

	// Ensure instruction has expected opcode
	if instruction.GetOpcode() != opcode {
		err = GuacamoleServerException.Throw("Expected \"" + opcode + "\" instruction but instead received \"" + instruction.GetOpcode() + "\".")
		return
	}
	return
}

/*NewConfiguredGuacamoleSocket2 *
* Creates a new ConfiguredGuacamoleSocket which uses the given
* GuacamoleConfiguration to complete the initial protocol handshake over
* the given GuacamoleSocket. A default GuacamoleClientInformation object
* is used to provide basic client information.
*
* @param socket The GuacamoleSocket to wrap.
* @param config The GuacamoleConfiguration to use to complete the initial
*               protocol handshake.
* @throws GuacamoleException If an error occurs while completing the
*                            initial protocol handshake.
 */
func NewConfiguredGuacamoleSocket2(socket GuacamoleSocket, config GuacamoleConfiguration) (ConfiguredGuacamoleSocket, ExceptionInterface) {
	return NewConfiguredGuacamoleSocket3(socket, config, NewGuacamoleClientInformation())
}

/*NewConfiguredGuacamoleSocket3 *
* Creates a new ConfiguredGuacamoleSocket which uses the given
* GuacamoleConfiguration and GuacamoleClientInformation to complete the
* initial protocol handshake over the given GuacamoleSocket.
*
* @param socket The GuacamoleSocket to wrap.
* @param config The GuacamoleConfiguration to use to complete the initial
*               protocol handshake.
* @param info The GuacamoleClientInformation to use to complete the initial
*             protocol handshake.
* @throws GuacamoleException If an error occurs while completing the
*                            initial protocol handshake.
 */
func NewConfiguredGuacamoleSocket3(socket GuacamoleSocket, config GuacamoleConfiguration, info GuacamoleClientInformation) (one ConfiguredGuacamoleSocket, err ExceptionInterface) {

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
	err = writer.WriteInstruction(NewGuacamoleInstruction("select", selectArg))
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
	err = writer.WriteInstruction(NewGuacamoleInstruction("size",
		fmt.Sprintf("%v", info.GetOptimalScreenWidth()),
		fmt.Sprintf("%v", info.GetOptimalScreenHeight()),
		fmt.Sprintf("%v", info.GetOptimalResolution())),
	)

	if err != nil {
		return
	}

	// Send supported audio formats
	err = writer.WriteInstruction(
		NewGuacamoleInstruction(
			"audio",
			info.GetAudioMimetypes()...,
		))
	if err != nil {
		return
	}

	// Send supported video formats
	err = writer.WriteInstruction(
		NewGuacamoleInstruction(
			"video",
			info.GetVideoMimetypes()...,
		))
	if err != nil {
		return
	}

	// Send supported image formats
	err = writer.WriteInstruction(
		NewGuacamoleInstruction(
			"image",
			info.GetImageMimetypes()...,
		))
	if err != nil {
		return
	}

	// Send args
	err = writer.WriteInstruction(NewGuacamoleInstruction("connect", argValueS...))
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
		err = GuacamoleServerException.Throw("No connection ID received")
		return
	}

	one.id = readyArgs[0]

	return

}

/*GetConfiguration *
* Returns the GuacamoleConfiguration used to configure this
* ConfiguredGuacamoleSocket.
*
* @return The GuacamoleConfiguration used to configure this
*         ConfiguredGuacamoleSocket.
 */
func (opt *ConfiguredGuacamoleSocket) GetConfiguration() GuacamoleConfiguration {
	return opt.config
}

/*GetConnectionID *
* Returns the unique ID associated with the Guacamole connection
* negotiated by this ConfiguredGuacamoleSocket. The ID is provided by
* the "ready" instruction returned by the Guacamole proxy.
*
* @return The ID of the negotiated Guacamole connection.
 */
func (opt *ConfiguredGuacamoleSocket) GetConnectionID() string {
	return opt.id
}

// GetWriter override GuacamoleSocket.GetWriter
func (opt *ConfiguredGuacamoleSocket) GetWriter() GuacamoleWriter {
	return opt.socket.GetWriter()
}

// GetReader override GuacamoleSocket.GetReader
func (opt *ConfiguredGuacamoleSocket) GetReader() GuacamoleReader {
	return opt.socket.GetReader()
}

// Close override GuacamoleSocket.Close
func (opt *ConfiguredGuacamoleSocket) Close() (err ExceptionInterface) {
	return opt.socket.Close()
}

// IsOpen override GuacamoleSocket.IsOpen
func (opt *ConfiguredGuacamoleSocket) IsOpen() bool {
	return opt.socket.IsOpen()
}
