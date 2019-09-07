package guac

import (
	"fmt"
	"net"
	"time"
)

// SocketTimeout socket timeout setting
//  * The number of milliseconds to wait for data on the TCP socket before
//  * timing out.
const SocketTimeout = 15 * time.Second

// InetGuacamoleSocket ==> GuacamoleSocket
// * Provides abstract socket-like access to a Guacamole connection over a given
// * hostname and port.
type InetGuacamoleSocket struct {
	reader GuacamoleReader
	write  GuacamoleWriter
	sock   net.Conn
}

// NewInetGuacamoleSocket Construct & connect
//  * Creates a new InetGuacamoleSocket which reads and writes instructions
//  * to the Guacamole instruction stream of the Guacamole proxy server
//  * running at the given hostname and port.
//  *
//  * @param hostname The hostname of the Guacamole proxy server to connect to.
//  * @param port The port of the Guacamole proxy server to connect to.
//  * @throws GuacamoleException If an error occurs while connecting to the
//  *                            Guacamole proxy server.
func NewInetGuacamoleSocket(hostname string, port int) (ret InetGuacamoleSocket, err ExceptionInterface) {
	// log.DebugF("Try connect %v:%v", hostname, port)

	// Get address
	address := fmt.Sprintf("%s:%d", hostname, port)
	addr, e := net.ResolveTCPAddr("tcp", address)

	// Connect with timeout
	// sock, e := net.DialTimeout("tcp", address, SocketTimeout)

	sock, e := net.DialTCP("tcp", nil, addr)
	if e != nil {
		err = GuacamoleUpstreamTimeoutException.Throw("Connection timed out.", e.Error())
		return
	}

	// Set read timeout
	// On successful connect, retrieve I/O streams
	stream := NewStream(sock, SocketTimeout)
	ret.sock = sock
	ret.reader = NewReaderGuacamoleReader(stream)
	ret.write = NewWriterGuacamoleWriter(stream)
	return
}

// Close Override GuacamoleSocket.Close
func (opt *InetGuacamoleSocket) Close() (err ExceptionInterface) {
	// logger.debug("Closing socket to guacd.");
	e := opt.sock.Close()
	if e != nil {
		err = GuacamoleServerException.Throw(e.Error())
	}
	return
}

// GetReader Override GuacamoleSocket.GetReader
func (opt *InetGuacamoleSocket) GetReader() (ret GuacamoleReader) {
	ret = opt.reader
	return
}

// GetWriter Override GuacamoleSocket.GetWriter
func (opt *InetGuacamoleSocket) GetWriter() (ret GuacamoleWriter) {
	ret = opt.write
	return
}

// IsOpen Override GuacamoleSocket.IsOpen
func (opt *InetGuacamoleSocket) IsOpen() (ok bool) {
	_, e := opt.sock.Write([]byte{})
	ok = e == nil
	return
}
