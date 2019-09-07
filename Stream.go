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

// Stream interface
type Stream struct {
	lock    sync.RWMutex
	core    net.Conn
	timeout time.Duration
	err     error
}

// NewStream Construct function
func NewStream(conn net.Conn, timeout time.Duration) (ret *Stream) {
	ret = &Stream{}
	ret.core = conn
	ret.timeout = timeout
	return
}

func (opt *Stream) errClose(err error) {
	opt.lock.Lock()
	defer opt.lock.Unlock()
	if opt.core == nil {
		return
	}
	opt.core.Close()
	opt.core = nil
	opt.err = err
	logger.Debug("close socket")
}

func (opt *Stream) Write(data []byte) (n int, err error) {
	if opt.err != nil {
		err = opt.err
		return
	}
	if opt.core == nil {
		err = net.ErrWriteToConnected
		return
	}
	if opt.timeout > 0 {
		if err = opt.core.SetWriteDeadline(time.Now().Add(opt.timeout)); err != nil {
			opt.errClose(err)
			return
		}
	}
	try := 0
	pos := 0
	for pos < len(data) {
		n, err = opt.core.Write(data[pos:])
		if err != nil {
			if en, ok := err.(net.Error); !ok || !en.Temporary() || try >= 3 {
				opt.errClose(err)
				return
			}
			try++
			continue
		}
		pos += n
	}
	if opt.timeout > 0 {
		if err = opt.core.SetWriteDeadline(time.Time{}); err != nil {
			opt.errClose(err)
			return
		}
	}
	return
}

func (opt *Stream) Read() (ret []byte, err error) {
	var n int
	if opt.err != nil {
		err = opt.err
		return
	}
	if opt.core == nil {
		err = net.ErrWriteToConnected
		return
	}
	if opt.timeout > 0 {
		if err = opt.core.SetReadDeadline(time.Now().Add(opt.timeout)); err != nil {
			// opt.errClose(err)
			return
		}
	}
	tmp := make([]byte, StepLength, StepLength)
	for try := 0; try < 3; try++ {
		n, err = opt.core.Read(tmp)
		if err != nil {
			ex, ok := err.(net.Error)
			if ok && ex.Temporary() {
				continue
			}
			return
		}
		break
	}

	if opt.timeout > 0 {
		if err = opt.core.SetReadDeadline(time.Time{}); err != nil {
			// opt.errClose(err)
			return
		}
	}
	ret = tmp[0:n]
	return
}

// Available stream check
func (opt *Stream) Available() (bool, error) {
	// ToDo here
	// Check if temp buffer is not empty
	return false, nil
}

// Close stream close
func (opt *Stream) Close() (err error) {
	opt.errClose(fmt.Errorf("Closed"))
	return
}
