package guac

import (
	"crypto/tls"
	"fmt"
	"net"
	"time"
)

// SocketTimeout stream timeout setting
//  * The number of milliseconds to wait for data on the TCP stream before
//  * timing out.
const SocketTimeout = 15 * time.Second

// NewInetSocket connects to Guacamole via non-tls dialer
func NewInetSocket(hostname string, port int) (*Stream, error) {
	address := fmt.Sprintf("%s:%d", hostname, port)
	addr, e := net.ResolveTCPAddr("tcp", address)

	conn, e := net.DialTCP("tcp", nil, addr)
	if e != nil {
		err := ErrUpstreamTimeout.NewError("Connection timed out.", e.Error())
		return nil, err
	}

	return NewStream(conn, SocketTimeout), nil
}

// NewSslSocket connects to Guacamole via a tls dialer
func NewSslSocket(hostname string, port int) (*Stream, error) {
	address := fmt.Sprintf("%s:%d", hostname, port)
	conn, err := tls.DialWithDialer(
		&net.Dialer{Timeout: SocketTimeout}, "tcp", address,
		&tls.Config{
			InsecureSkipVerify: true,
		})
	if err != nil {
		return nil, err
	}

	return NewStream(conn, SocketTimeout), nil
}
