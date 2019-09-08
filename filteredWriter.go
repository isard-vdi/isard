package guac

// Move FilteredWriter from protocol folder to here
// Avoid cross depends

// FilteredWriter ==> Writer
//  * Writer which applies a given Filter to observe or alter
//  * all written instructions. Instructions may also be dropped or denied by
//  * the filter.
type FilteredWriter struct {
	/**
	 * The wrapped Writer.
	 */
	writer Writer

	/**
	 * The filter to apply when writing instructions.
	 */
	filter Filter

	/**
	 * Parser for reading instructions prior to writing, such that they can be
	 * passed on to the filter.
	 */
	parser Parser
}

// NewFilteredWriter *
// * Wraps the given Writer, applying the given filter to all written
// * instructions. Future writes will only write instructions which pass
// * the filter.
// *
// * @param writer The Writer to wrap.
// * @param filter The filter which dictates which instructions are written,
// *               and how.
func NewFilteredWriter(writer Writer, filter Filter) (ret FilteredWriter) {
	ret.writer = writer
	ret.filter = filter
	ret.parser = NewGuacamoleParser()
	return
}

// Write override Writer.Write
func (opt *FilteredWriter) Write(chunk []byte, offset, length int) (err error) {
	for length > 0 {
		var parsed int
		for parsed, err = opt.parser.Append(chunk, offset, length); parsed > 0 && err == nil; parsed, err = opt.parser.Append(chunk, offset, length) {
			offset += parsed
			length -= parsed
		}
		if err != nil {
			return
		}
		if !opt.parser.HasNext() {
			err = ErrServer.NewError("Filtered write() contained an incomplete instruction.")
			return
		}

		if v, ok := opt.parser.Next(); ok {
			err = opt.WriteInstruction(v)
			if err != nil {
				return
			}
		}
	}
	return
}

// WriteAll override Writer.WriteAll
func (opt *FilteredWriter) WriteAll(chunk []byte) (err error) {
	return opt.Write(chunk, 0, len(chunk))
}

// WriteInstruction override Writer.WriteInstruction
func (opt *FilteredWriter) WriteInstruction(instruction Instruction) (err error) {

	// Write instruction only if not dropped
	filteredInstruction, err := opt.filter.Filter(instruction)
	if err != nil {
		return
	}
	if len(filteredInstruction.GetOpcode()) > 0 {
		err = opt.writer.WriteInstruction(filteredInstruction)
	}
	return
}
