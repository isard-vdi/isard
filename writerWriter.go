package guac

import (
	"net"
)

// WriterWriter A Writer which wraps a standard Java Writer,
// using that Writer as the Guacamole instruction stream.
type WriterWriter struct {
	output *Stream
}

// NewWriterWriter Constuct function
//  * Creates a new WriterWriter which will use the given Writer as
//  * the Guacamole instruction stream.
//  *
//  * @param output The Writer to use as the Guacamole instruction stream.
func NewWriterWriter(output *Stream) (ret Writer) {
	one := WriterWriter{}
	one.output = output
	ret = &one
	return
}

// Write override Writer.Write
func (opt *WriterWriter) Write(chunk []byte, off, l int) (err error) {
	if len(chunk) < off+l {
		err = ErrServer.NewError("Input buffer size smaller than required")
		return
	}
	e := opt.WriteAll(chunk[off : off+l])
	if e != nil {
		// Socket timeout will close so ...
		err = ErrConnectionClosed.NewError("Connection to guacd is closed.", e.Error())
	}
	return
}

// WriteAll override Writer.WriteAll
func (opt *WriterWriter) WriteAll(chunk []byte) (err error) {
	_, e := opt.output.Write(chunk)
	if e == nil {
		return
	}
	switch e.(type) {
	case net.Error:
		ex := e.(net.Error)
		if ex.Timeout() {
			err = ErrUpstreamTimeout.NewError("Connection to guacd timed out.", e.Error())
		} else {
			err = ErrConnectionClosed.NewError("Connection to guacd is closed.", e.Error())
		}
	default:
		err = ErrServer.NewError(e.Error())
	}
	return
}

// WriteInstruction override Writer.WriteInstruction
func (opt *WriterWriter) WriteInstruction(instruction Instruction) (err error) {
	return opt.WriteAll([]byte(instruction.String()))
}
