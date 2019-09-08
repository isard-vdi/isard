package guac

// In java
// public class Parser implements Iterator<Instruction>
// But not use it as Iterator, More like more parser
// So discard Iterator keep method

const (
	/*INSTRUCTION_MAX_LENGTH *
	 * The maximum number of characters per instruction.
	 */
	InstructionMaxLength = 8192

	/*INSTRUCTION_MAX_DIGITS *
	 * The maximum number of digits to allow per length prefix.
	 */
	InstructionMaxDigits = 5

	/*INSTRUCTION_MAX_ELEMENTS *
	 * The maximum number of elements per instruction, including the opcode.
	 */
	InstructionMaxElements = 64
)

// ParserState All possible states of the instruction parser.
type ParserState int

const (
	/*PARSING_LENGTH *
	 * The parser is currently waiting for data to complete the length prefix
	 * of the current element of the instruction.
	 */
	ParsingLength ParserState = iota

	/*PARSING_CONTENT *
	 * The parser has finished reading the length prefix and is currently
	 * waiting for data to complete the content of the instruction.
	 */
	ParsingContent

	/*Complete *
	 * The instruction has been fully parsed.
	 */
	Complete

	/*Error *
	 * The instruction cannot be parsed because of a protocol error.
	 */
	Error
)

func (state ParserState) String() (ret string) {
	switch state {
	case ParsingLength:
		ret = "PARSING_LENGTH"
	case ParsingContent:
		ret = "PARSING_CONTENT"
	case Complete:
		ret = "Complete"
	case Error:
		ret = "Error"
	}
	return
}

// Parser *
//  * Parser for the Guacamole protocol. Arbitrary instruction data is appended,
//  * and instructions are returned as a result. Invalid instructions result in
//  * exceptions.
type Parser struct {
	/**
	 * The latest parsed instruction, if any.
	 */
	parsedInstruction Instruction

	/**
	 * The parse state of the instruction.
	 */
	state ParserState

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

func NewGuacamoleParser() (ret Parser) {
	ret.init()
	return
}

func (opt *Parser) init() {
	opt.parsedInstruction = NewInstruction("")
	opt.state = ParsingLength
	opt.elementLength = 0
	opt.elements = make([]string, 0, InstructionMaxElements)
}

// Append *
// * Appends data from the given buffer to the current instruction.
// *
// * @param chunk The data to append.
// * @return The number of characters appended, or 0 if complete instructions
// *         have already been parsed and must be read via next() before
// *         more data can be appended.
// * @throws GuacamoleException If an error occurs while parsing the new data.
func (opt *Parser) Append(chunk []byte, offset, length int) (charsParsed int, err ExceptionInterface) {
	charsParsed = 0

	// Do not exceed maximum number of elements
	if len(opt.elements) >= InstructionMaxElements && opt.state != Complete {
		opt.state = Error
		err = ServerException.Throw("Instruction contains too many elements.")
		return
	}

	// Parse element length
	if opt.state == ParsingLength {

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
				opt.state = ParsingContent
				break loop
			default:
				opt.state = Error
				err = ServerException.Throw("Non-numeric character in element length.")
				return
			}

		}

		// If too long, parse error
		if parsedLength > InstructionMaxLength {
			opt.state = Error
			err = ServerException.Throw("Instruction exceeds maximum length.")
			return
		}

		// Save length
		opt.elementLength = parsedLength

	} // end parse length

	// Parse element content, if available
	if opt.state == ParsingContent && charsParsed+opt.elementLength+1 <= length {

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
			opt.state = Complete
			opt.parsedInstruction = NewInstruction(opt.elements[0], opt.elements[1:]...)
		case ',':
			opt.state = ParsingLength

		default:
			opt.state = Error
			err = ServerException.Throw("Element terminator of instruction was not ';' nor ','")
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
func (opt *Parser) AppendAll(chunk []byte) (charsParsed int, err ExceptionInterface) {
	return opt.Append(chunk, 0, len(chunk))
}

// HasNext Check One complete
func (opt *Parser) HasNext() bool {
	return opt.state == Complete
}

// Next Fetch data from parser
func (opt *Parser) Next() (ret Instruction, ok bool) {

	// No instruction to return if not yet complete
	if opt.state != Complete {
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
//    throw new UnsupportedOperationException("Parser does not support remove().");
//}
