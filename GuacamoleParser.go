package guac

// In java
// public class GuacamoleParser implements Iterator<GuacamoleInstruction>
// But not use it as Iterator, More like more parser
// So discard Iterator keep method

const (
	/*INSTRUCTION_MAX_LENGTH *
	 * The maximum number of characters per instruction.
	 */
	INSTRUCTION_MAX_LENGTH = 8192

	/*INSTRUCTION_MAX_DIGITS *
	 * The maximum number of digits to allow per length prefix.
	 */
	INSTRUCTION_MAX_DIGITS = 5

	/*INSTRUCTION_MAX_ELEMENTS *
	 * The maximum number of elements per instruction, including the opcode.
	 */
	INSTRUCTION_MAX_ELEMENTS = 64
)

// GuacamoleParserState All possible states of the instruction parser.
type GuacamoleParserState int

const (
	/*PARSING_LENGTH *
	 * The parser is currently waiting for data to complete the length prefix
	 * of the current element of the instruction.
	 */
	PARSING_LENGTH GuacamoleParserState = iota

	/*PARSING_CONTENT *
	 * The parser has finished reading the length prefix and is currently
	 * waiting for data to complete the content of the instruction.
	 */
	PARSING_CONTENT

	/*COMPLETE *
	 * The instruction has been fully parsed.
	 */
	COMPLETE

	/*ERROR *
	 * The instruction cannot be parsed because of a protocol error.
	 */
	ERROR
)

func (state GuacamoleParserState) String() (ret string) {
	switch state {
	case PARSING_LENGTH:
		ret = "PARSING_LENGTH"
	case PARSING_CONTENT:
		ret = "PARSING_CONTENT"
	case COMPLETE:
		ret = "COMPLETE"
	case ERROR:
		ret = "ERROR"
	}
	return
}

// GuacamoleParser *
//  * Parser for the Guacamole protocol. Arbitrary instruction data is appended,
//  * and instructions are returned as a result. Invalid instructions result in
//  * exceptions.
type GuacamoleParser struct {
	/**
	 * The latest parsed instruction, if any.
	 */
	parsedInstruction GuacamoleInstruction

	/**
	 * The parse state of the instruction.
	 */
	state GuacamoleParserState

	/**
	 * The length of the current element, if known.
	 */
	elementLength int

	/**
	 * The number of elements currently parsed.
	 */
	// Instead of len(elements)
	// elementCount int

	/**
	 * All currently parsed elements.
	 */
	elements []string
}

func NewGuacamoleParser() (ret GuacamoleParser) {
	ret.init()
	return
}

func (opt *GuacamoleParser) init() {
	opt.parsedInstruction = NewGuacamoleInstruction("")
	opt.state = PARSING_LENGTH
	opt.elementLength = 0
	opt.elements = make([]string, 0, INSTRUCTION_MAX_ELEMENTS)
}

// Append *
// * Appends data from the given buffer to the current instruction.
// *
// * @param chunk The data to append.
// * @return The number of characters appended, or 0 if complete instructions
// *         have already been parsed and must be read via next() before
// *         more data can be appended.
// * @throws GuacamoleException If an error occurs while parsing the new data.
func (opt *GuacamoleParser) Append(chunk []byte, offset, length int) (charsParsed int, err ExceptionInterface) {
	charsParsed = 0

	// Do not exceed maximum number of elements
	if len(opt.elements) >= INSTRUCTION_MAX_ELEMENTS && opt.state != COMPLETE {
		opt.state = ERROR
		err = GuacamoleServerException.Throw("Instruction contains too many elements.")
		return
	}

	// Parse element length
	if opt.state == PARSING_LENGTH {

		parsedLength := opt.elementLength

	loop:
		for charsParsed < length {

			// Pull next character
			c := chunk[offset+charsParsed]
			charsParsed++

			// If digit, add to length
			switch c {
			case '0', '1', '2', '3', '4', '5', '6', '7', '8', '9':
				parsedLength = parsedLength*10 + int(c-'0')
			case '.':
				opt.state = PARSING_CONTENT
				break loop
			default:
				opt.state = ERROR
				err = GuacamoleServerException.Throw("Non-numeric character in element length.")
				return
			}

		}

		// If too long, parse error
		if parsedLength > INSTRUCTION_MAX_LENGTH {
			opt.state = ERROR
			err = GuacamoleServerException.Throw("Instruction exceeds maximum length.")
			return
		}

		// Save length
		opt.elementLength = parsedLength

	} // end parse length

	// Parse element content, if available
	if opt.state == PARSING_CONTENT && charsParsed+opt.elementLength+1 <= length {

		// Read element
		element := string(chunk[offset+charsParsed : offset+charsParsed+opt.elementLength])
		charsParsed += opt.elementLength
		opt.elementLength = 0

		// Read terminator char following element
		terminator := chunk[offset+charsParsed]
		charsParsed++

		// Add element to currently parsed elements
		// Instread  elements[elementCount++] = element;
		opt.elements = append(opt.elements, element)

		// If semicolon, store end-of-instruction
		switch terminator {
		case ';':
			opt.state = COMPLETE
			opt.parsedInstruction = NewGuacamoleInstruction(opt.elements[0], opt.elements[1:]...)
		case ',':
			opt.state = PARSING_LENGTH

		default:
			opt.state = ERROR
			err = GuacamoleServerException.Throw("Element terminator of instruction was not ';' nor ','")
			return
		}

	} // end parse content

	return
}

// AppendAll *
// * Appends data from the given buffer to the current instruction.
// *
// * @param chunk The data to append.
// * @return The number of characters appended, or 0 if complete instructions
// *         have already been parsed and must be read via next() before
// *         more data can be appended.
// * @throws GuacamoleException If an error occurs while parsing the new data.
func (opt *GuacamoleParser) AppendAll(chunk []byte) (charsParsed int, err ExceptionInterface) {
	return opt.Append(chunk, 0, len(chunk))
}

// HasNext Check One complete
func (opt *GuacamoleParser) HasNext() bool {
	return opt.state == COMPLETE
}

// Next Fetch data from parser
func (opt *GuacamoleParser) Next() (ret GuacamoleInstruction, ok bool) {

	// No instruction to return if not yet complete
	if opt.state != COMPLETE {
		return
	}

	ret = opt.parsedInstruction
	ok = true

	// Reset for next instruction.
	opt.init()

	return

}

//@Override
//public void remove() {
//    throw new UnsupportedOperationException("GuacamoleParser does not support remove().");
//}
