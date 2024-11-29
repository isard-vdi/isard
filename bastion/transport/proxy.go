package transport

import (
	"io"
	"net"
	"time"
)

func Proxy(dst io.ReadWriter, src io.ReadWriter) chan error {
	ioErr := make(chan error, 2)

	go proxy(dst, src, ioErr)
	go proxy(src, dst, ioErr)

	return ioErr
}

func proxy(dst io.Writer, src io.Reader, ioErr chan error) {
	_, err := io.Copy(dst, src)
	ioErr <- err
}

// Stolen from https://www.agwa.name/blog/post/writing_an_sni_proxy_in_go
type ReadOnlyConn struct {
	Reader io.Reader
}

func (conn ReadOnlyConn) Read(p []byte) (int, error)         { return conn.Reader.Read(p) }
func (conn ReadOnlyConn) Write(p []byte) (int, error)        { return 0, io.ErrClosedPipe }
func (conn ReadOnlyConn) Close() error                       { return nil }
func (conn ReadOnlyConn) LocalAddr() net.Addr                { return nil }
func (conn ReadOnlyConn) RemoteAddr() net.Addr               { return nil }
func (conn ReadOnlyConn) SetDeadline(t time.Time) error      { return nil }
func (conn ReadOnlyConn) SetReadDeadline(t time.Time) error  { return nil }
func (conn ReadOnlyConn) SetWriteDeadline(t time.Time) error { return nil }
