package guac

import (
	"crypto/tls"
	"fmt"
	"io"
	"net"
)

// SslSocket ==> Socket
// * Provides abstract socket-like access to a Guacamole connection over a given
// * hostname and port.
type SslSocket struct {
	reader Reader
	write  io.Writer
	sock   *tls.Conn
}

// NewSslSocket Construct & connect
//  * Creates a new InetSocket which reads and writes instructions
//  * to the Guacamole instruction stream of the Guacamole proxy server
//  * running at the given hostname and port.
//  *
//  * @param hostname The hostname of the Guacamole proxy server to connect to.
//  * @param port The port of the Guacamole proxy server to connect to.
//  * @throws ErrOther If an error occurs while connecting to the
//  *                            Guacamole proxy server.
func NewSslSocket(hostname string, port int) (ret SslSocket, err error) {
	// log.DebugF("Connecting to guacd at {}:{} via SSL/TLS.", hostname, port)

	// Get address
	address := fmt.Sprintf("%s:%d", hostname, port)

	// Connect with timeout
	sock, err := tls.DialWithDialer(
		&net.Dialer{Timeout: SocketTimeout}, "tcp", address,
		&tls.Config{
			InsecureSkipVerify: true,
		})
	if err != nil {
		// throw new ErrUpstreamTimeout("Connection timed out.", e);
		return
	}

	// Set read timeout
	// On successful connect, retrieve I/O streams
	stream := NewStream(sock, SocketTimeout)
	ret.sock = sock
	ret.reader = NewInstructionReader(stream)
	ret.write = stream
	return
}

// Close Override Socket.Close
func (opt *SslSocket) Close() (err error) {
	// logger.debug("Closing socket to guacd.");
	e := opt.sock.Close()
	if e != nil {
		err = ErrServer.NewError(e.Error())
	}
	return
}

// GetReader Override Socket.GetReader
func (opt *SslSocket) GetReader() (ret Reader) {
	ret = opt.reader
	return
}

// GetWriter Override Socket.GetWriter
func (opt *SslSocket) GetWriter() (ret io.Writer) {
	ret = opt.write
	return
}

// IsOpen Override Socket.IsOpen
func (opt *SslSocket) IsOpen() (ok bool) {
	_, e := opt.sock.Write([]byte{})
	ok = e == nil
	return
}
