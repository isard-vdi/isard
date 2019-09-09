package guac

import (
	logger "github.com/sirupsen/logrus"
	"net"
	"time"
)

// Step value
const (
	StepLength = 1024
)

type Stream struct {
	conn    net.Conn
	timeout time.Duration
}

// NewStream Construct function
func NewStream(conn net.Conn, timeout time.Duration) (ret *Stream) {
	ret = &Stream{}
	ret.conn = conn
	ret.timeout = timeout
	return
}

func (s *Stream) Write(data []byte) (n int, err error) {
	if err = s.conn.SetWriteDeadline(time.Now().Add(s.timeout)); err != nil {
		logger.Error(err)
		return
	}
	return s.conn.Write(data)
}

func (s *Stream) Read(p []byte) (n int, err error) {
	if err = s.conn.SetReadDeadline(time.Now().Add(s.timeout)); err != nil {
		logger.Error(err)
		return
	}
	return s.conn.Read(p)
}

// Available stream check
func (s *Stream) Available() (bool, error) {
	// ToDo here
	// Check if temp buffer is not empty
	return false, nil
}

// Close stream close
func (s *Stream) Close() (err error) {
	return s.conn.Close()
}
