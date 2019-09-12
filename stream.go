package guac

import (
	logger "github.com/sirupsen/logrus"
	"net"
	"time"
)

// Step value
const (
	StepLength = 64
)

type Stream struct {
	net.Conn
	timeout time.Duration
}

// NewStream Construct function
func NewStream(conn net.Conn, timeout time.Duration) (ret *Stream) {
	ret = &Stream{}
	ret.Conn = conn
	ret.timeout = timeout
	return
}

func (s *Stream) Write(data []byte) (n int, err error) {
	if err = s.Conn.SetWriteDeadline(time.Now().Add(s.timeout)); err != nil {
		logger.Error(err)
		return
	}
	return s.Conn.Write(data)
}

func (s *Stream) Read(p []byte) (n int, err error) {
	if err = s.Conn.SetReadDeadline(time.Now().Add(s.timeout)); err != nil {
		logger.Error(err)
		return
	}
	return s.Conn.Read(p)
}
