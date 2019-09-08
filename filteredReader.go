package guac

// FilteredReader ==> Reader
type FilteredReader struct {
	/**
	 * The wrapped Reader.
	 */
	reader Reader

	/**
	 * The filter to apply when reading instructions.
	 */
	filter Filter
}

/*NewFilteredReader *
* Wraps the given Reader, applying the given filter to all read
* instructions. Future reads will return only instructions which pass
* the filter.
*
* @param reader The Reader to wrap.
* @param filter The filter which dictates which instructions are read, and
*               how.
 */
func NewFilteredReader(reader Reader, filter Filter) *FilteredReader {
	return &FilteredReader{
		reader: reader,
		filter: filter,
	}
}

// Available override Reader.Available
func (opt *FilteredReader) Available() (ok bool, err error) {
	return opt.reader.Available()
}

// Read override Reader.Read
func (opt *FilteredReader) Read() (ret []byte, err error) {
	filteredInstruction, err := opt.ReadInstruction()
	if err != nil {
		return
	}
	ret = []byte(filteredInstruction.String())
	return
}

// ReadInstruction override Reader.ReadInstruction
func (opt *FilteredReader) ReadInstruction() (ret Instruction, err error) {
	var filteredInstruction Instruction

	for len(filteredInstruction.GetOpcode()) == 0 {
		filteredInstruction, err = opt.reader.ReadInstruction()
		if err != nil {
			return
		}
		if len(filteredInstruction.GetOpcode()) == 0 {
			return
		}
		filteredInstruction, err = opt.filter.Filter(filteredInstruction)
		if err != nil {
			return
		}
	}
	ret = filteredInstruction
	return
}
