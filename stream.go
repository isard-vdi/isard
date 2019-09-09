package guac

import (
	"fmt"
	logger "github.com/sirupsen/logrus"
	"net"
	"sync"
	"time"
)

// Step value
const (
	StepLength = 1024
)

type Stream struct {
	lock    sync.RWMutex
	conn    net.Conn
	timeout time.Duration
	err     error
}

// NewStream Construct function
func NewStream(conn net.Conn, timeout time.Duration) (ret *Stream) {
	ret = &Stream{}
	ret.conn = conn
	ret.timeout = timeout
	return
}

func (s *Stream) errClose(err error) {
	s.lock.Lock()
	defer s.lock.Unlock()
	if s.conn == nil {
		return
	}
	_ = s.conn.Close()
	s.conn = nil
	s.err = err
	logger.Debug("close socket")
}

func (s *Stream) Write(data []byte) (n int, err error) {
	if s.err != nil {
		err = s.err
		return
	}
	if s.conn == nil {
		err = net.ErrWriteToConnected
		return
	}
	if s.timeout > 0 {
		if err = s.conn.SetWriteDeadline(time.Now().Add(s.timeout)); err != nil {
			s.errClose(err)
			return
		}
	}
	try := 0
	pos := 0
	for pos < len(data) {
		n, err = s.conn.Write(data[pos:])
		if err != nil {
			if en, ok := err.(net.Error); !ok || !en.Temporary() || try >= 3 {
				s.errClose(err)
				return
			}
			try++
			continue
		}
		pos += n
	}
	if s.timeout > 0 {
		if err = s.conn.SetWriteDeadline(time.Time{}); err != nil {
			s.errClose(err)
			return
		}
	}
	return
}

func (s *Stream) Read(p []byte) (n int, err error) {
	if s.err != nil {
		err = s.err
		return
	}
	if s.conn == nil {
		err = net.ErrWriteToConnected
		return
	}
	if s.timeout > 0 {
		if err = s.conn.SetReadDeadline(time.Now().Add(s.timeout)); err != nil {
			// s.errClose(err)
			return
		}
	}
	for try := 0; try < 3; try++ {
		n, err = s.conn.Read(p)
		if err != nil {
			ex, ok := err.(net.Error)
			if ok && ex.Temporary() {
				continue
			}
			return
		}
		break
	}

	if s.timeout > 0 {
		if err = s.conn.SetReadDeadline(time.Time{}); err != nil {
			// s.errClose(err)
			return
		}
	}
	return
}

// Available stream check
func (s *Stream) Available() (bool, error) {
	// ToDo here
	// Check if temp buffer is not empty
	return false, nil
}

// Close stream close
func (s *Stream) Close() (err error) {
	s.errClose(fmt.Errorf("closed"))
	return
}
