package guac

import (
	"net"
)

// WriterGuacamoleWriter A GuacamoleWriter which wraps a standard Java Writer,
// using that Writer as the Guacamole instruction stream.
type WriterGuacamoleWriter struct {
	output *Stream
}

// NewWriterGuacamoleWriter Constuct function
//  * Creates a new WriterGuacamoleWriter which will use the given Writer as
//  * the Guacamole instruction stream.
//  *
//  * @param output The Writer to use as the Guacamole instruction stream.
func NewWriterGuacamoleWriter(output *Stream) (ret GuacamoleWriter) {
	one := WriterGuacamoleWriter{}
	one.output = output
	ret = &one
	return
}

// Write override GuacamoleWriter.Write
func (opt *WriterGuacamoleWriter) Write(chunk []byte, off, l int) (err ExceptionInterface) {
	if len(chunk) < off+l {
		err = GuacamoleServerException.Throw("Input buffer size smaller than required")
		return
	}
	e := opt.WriteAll(chunk[off : off+l])
	if e != nil {
		// Socket timeout will close so ...
		err = GuacamoleConnectionClosedException.Throw("Connection to guacd is closed.", e.Error())
	}
	return
}

// WriteAll override GuacamoleWriter.WriteAll
func (opt *WriterGuacamoleWriter) WriteAll(chunk []byte) (err ExceptionInterface) {
	_, e := opt.output.Write(chunk)
	if e == nil {
		return
	}
	switch e.(type) {
	case net.Error:
		ex := e.(net.Error)
		if ex.Timeout() {
			err = GuacamoleUpstreamTimeoutException.Throw("Connection to guacd timed out.", e.Error())
		} else {
			err = GuacamoleConnectionClosedException.Throw("Connection to guacd is closed.", e.Error())
		}
	default:
		err = GuacamoleServerException.Throw(e.Error())
	}
	return
}

// WriteInstruction override GuacamoleWriter.WriteInstruction
func (opt *WriterGuacamoleWriter) WriteInstruction(instruction GuacamoleInstruction) (err ExceptionInterface) {
	return opt.WriteAll([]byte(instruction.String()))
}
