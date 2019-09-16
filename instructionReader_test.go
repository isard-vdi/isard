package guac

import (
	"bytes"
	"io"
	"net"
	"testing"
	"time"
)

func TestInstructionReader_ReadSome(t *testing.T) {
	conn := &fakeConn{
		ToRead: []byte("4.copy,2.ab;4.copy"),
	}
	reader := NewInstructionReader(NewStream(conn, 1*time.Minute))

	ins, err := reader.ReadSome()

	if err != nil {
		t.Error("Unexpected error", err)
	}
	if !bytes.Equal(ins, []byte("4.copy,2.ab;")) {
		t.Error("Unexpected bytes returned")
	}

	// Read some more to simulate data being fragmented
	copy(conn.ToRead, ",2.ab;")
	conn.HasRead = false
	ins, err = reader.ReadSome()

	if err != nil {
		t.Error("Unexpected error", err)
	}
	if !bytes.Equal(ins, []byte("4.copy,2.ab;")) {
		t.Error("Unexpected bytes returned")
	}
}

func TestInstructionReader_Flush(t *testing.T) {
	r := NewInstructionReader(NewStream(&fakeConn{}, time.Second))
	r.buffer = r.buffer[:4]
	r.buffer[0] = '1'
	r.buffer[1] = '2'
	r.buffer[2] = '3'
	r.buffer[3] = '4'
	r.buffer = r.buffer[2:]

	r.Flush()

	if r.buffer[0] != '3' && r.buffer[1] != '4' {
		t.Error("Unexpected buffer contents:", string(r.buffer[:2]))
	}
}

type fakeConn struct {
	ToRead  []byte
	HasRead bool
	Closed  bool
}

func (f *fakeConn) Read(b []byte) (n int, err error) {
	if f.HasRead {
		return 0, io.EOF
	} else {
		f.HasRead = true
		return copy(b, f.ToRead), nil
	}
}

func (f *fakeConn) Write(b []byte) (n int, err error) {
	return 0, nil
}

func (f *fakeConn) Close() error {
	f.Closed = true
	return nil
}

func (f *fakeConn) LocalAddr() net.Addr {
	return nil
}

func (f *fakeConn) RemoteAddr() net.Addr {
	return nil
}

func (f *fakeConn) SetDeadline(t time.Time) error {
	return nil
}

func (f *fakeConn) SetReadDeadline(t time.Time) error {
	return nil
}

func (f *fakeConn) SetWriteDeadline(t time.Time) error {
	return nil
}
