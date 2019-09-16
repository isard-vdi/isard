package guac

import (
	"fmt"
	"io"
)

type Config struct {
	ConnectionID string
	Protocol     string
	Parameters   map[string]string
}

func NewGuacamoleConfiguration() *Config {
	return &Config{
		Parameters: make(map[string]string),
	}
}

type ClientInfo struct {
	OptimalScreenWidth  int
	OptimalScreenHeight int
	OptimalResolution   int
	AudioMimetypes      []string
	VideoMimetypes      []string
	ImageMimetypes      []string
}

// NewGuacamoleClientInformation Construct function
func NewGuacamoleClientInformation() *ClientInfo {
	return &ClientInfo{
		OptimalScreenWidth:  1024,
		OptimalScreenHeight: 768,
		OptimalResolution:   96,
		AudioMimetypes:      make([]string, 0, 1),
		VideoMimetypes:      make([]string, 0, 1),
		ImageMimetypes:      make([]string, 0, 1),
	}
}

func assertOpcode(reader *InstructionReader, opcode string) (instruction *Instruction, err error) {
	instruction, err = reader.ReadOne()
	if err != nil {
		return
	}

	if len(instruction.Opcode) == 0 {
		err = ErrServer.NewError("End of stream while waiting for \"" + opcode + "\".")
		return
	}

	if instruction.Opcode != opcode {
		err = ErrServer.NewError("Expected \"" + opcode + "\" instruction but instead received \"" + instruction.Opcode + "\".")
		return
	}
	return
}

func ConfigureSocket(socket *Socket, config *Config, info *ClientInfo) error {
	// Get protocol / connection ID
	selectArg := config.ConnectionID
	if len(selectArg) == 0 {
		selectArg = config.Protocol
	}

	// Send requested protocol or connection ID
	_, err := writeInstruction(socket, NewInstruction("select", selectArg))
	if err != nil {
		return err
	}

	// Wait for server Args
	args, err := assertOpcode(socket.InstructionReader, "args")
	if err != nil {
		return err
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
	_, err = writeInstruction(socket, NewInstruction("size",
		fmt.Sprintf("%v", info.OptimalScreenWidth),
		fmt.Sprintf("%v", info.OptimalScreenHeight),
		fmt.Sprintf("%v", info.OptimalResolution)),
	)

	if err != nil {
		return err
	}

	// Send supported audio formats
	_, err = writeInstruction(socket, NewInstruction("audio", info.AudioMimetypes...))
	if err != nil {
		return err
	}

	// Send supported video formats
	_, err = writeInstruction(socket, NewInstruction("video", info.VideoMimetypes...))
	if err != nil {
		return err
	}

	// Send supported image formats
	_, err = writeInstruction(socket, NewInstruction("image", info.ImageMimetypes...))
	if err != nil {
		return err
	}

	// Send Args
	_, err = writeInstruction(socket, NewInstruction("connect", argValueS...))
	if err != nil {
		return err
	}

	// Wait for ready, store ID
	ready, err := assertOpcode(socket.InstructionReader, "ready")
	if err != nil {
		return err
	}

	readyArgs := ready.Args
	if len(readyArgs) == 0 {
		err = ErrServer.NewError("No connection ID received")
		return err
	}

	socket.InstructionReader.Flush()

	//socket.SetId(readyArgs[0])

	return nil
}

func writeInstruction(writer io.Writer, instruction *Instruction) (int, error) {
	return writer.Write([]byte(instruction.String()))
}
