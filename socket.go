package guac

import (
	"crypto/tls"
	"fmt"
	"net"
	"time"
)

// SocketTimeout socket timeout setting
//  * The number of milliseconds to wait for data on the TCP socket before
//  * timing out.
const SocketTimeout = 15 * time.Second

// Socket provides abstract socket-like access to a Guacamole connection.
type Socket struct {
	*InstructionReader
	*Stream
}

// NewInetSocket connects to Guacamole
func NewInetSocket(hostname string, port int) (*Socket, error) {
	address := fmt.Sprintf("%s:%d", hostname, port)
	addr, e := net.ResolveTCPAddr("tcp", address)

	conn, e := net.DialTCP("tcp", nil, addr)
	if e != nil {
		err := ErrUpstreamTimeout.NewError("Connection timed out.", e.Error())
		return nil, err
	}

	stream := NewStream(conn, SocketTimeout)
	return &Socket{
		Stream: stream,
		InstructionReader: NewInstructionReader(stream),
	}, nil
}

// NewSslSocket connects to Guacamole
func NewSslSocket(hostname string, port int) (*Socket, error) {
	address := fmt.Sprintf("%s:%d", hostname, port)
	conn, err := tls.DialWithDialer(
		&net.Dialer{Timeout: SocketTimeout}, "tcp", address,
		&tls.Config{
			InsecureSkipVerify: true,
		})
	if err != nil {
		return nil, err
	}

	// Set read timeout
	// On successful connect, retrieve I/O streams
	stream := NewStream(conn, SocketTimeout)
	return &Socket{
		Stream: stream,
		InstructionReader: NewInstructionReader(stream),
	}, nil
}
