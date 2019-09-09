package guac

import (
	"fmt"
	"io"
	"net"
	"time"
)

// SocketTimeout socket timeout setting
//  * The number of milliseconds to wait for data on the TCP socket before
//  * timing out.
const SocketTimeout = 15 * time.Second

// InetSocket ==> Socket
// * Provides abstract socket-like access to a Guacamole connection over a given
// * hostname and port.
type InetSocket struct {
	reader Reader
	write  io.Writer
	sock   net.Conn
}

// NewInetSocket Construct & connect
//  * Creates a new InetSocket which reads and writes instructions
//  * to the Guacamole instruction stream of the Guacamole proxy server
//  * running at the given hostname and port.
//  *
//  * @param hostname The hostname of the Guacamole proxy server to connect to.
//  * @param port The port of the Guacamole proxy server to connect to.
//  * @throws ErrOther If an error occurs while connecting to the
//  *                            Guacamole proxy server.
func NewInetSocket(hostname string, port int) (ret InetSocket, err error) {
	// log.DebugF("Try connect %v:%v", hostname, port)

	// Get address
	address := fmt.Sprintf("%s:%d", hostname, port)
	addr, e := net.ResolveTCPAddr("tcp", address)

	// Connect with timeout
	// sock, e := net.DialTimeout("tcp", address, SocketTimeout)

	sock, e := net.DialTCP("tcp", nil, addr)
	if e != nil {
		err = ErrUpstreamTimeout.NewError("Connection timed out.", e.Error())
		return
	}

	// Set read timeout
	// On successful connect, retrieve I/O streams
	stream := NewStream(sock, SocketTimeout)
	ret.sock = sock
	ret.reader = NewReaderReader(stream)
	ret.write = stream
	return
}

// Close Override Socket.Close
func (opt *InetSocket) Close() (err error) {
	// logger.debug("Closing socket to guacd.");
	e := opt.sock.Close()
	if e != nil {
		err = ErrServer.NewError(e.Error())
	}
	return
}

// GetReader Override Socket.GetReader
func (opt *InetSocket) GetReader() (ret Reader) {
	ret = opt.reader
	return
}

// GetWriter Override Socket.GetWriter
func (opt *InetSocket) GetWriter() (ret io.Writer) {
	ret = opt.write
	return
}

// IsOpen Override Socket.IsOpen
func (opt *InetSocket) IsOpen() (ok bool) {
	_, e := opt.sock.Write([]byte{})
	ok = e == nil
	return
}
