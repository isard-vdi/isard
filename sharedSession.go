package guac

import (
	"bytes"
	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
	"strings"
	"sync"
	"time"
)

type SharedSession struct {
	// lock for channels
	sync.RWMutex
	// the connection to guac
	Tunnel
	// messages to send to connected websockets
	channels []chan []byte
	// messages to send to guac
	writeChannel chan []byte
	// When additional clients connect they miss out on important messages.
	// Since I don't know what messages are important yet, I just gather up
	// a certain amount of the first messages and send them. This needs to
	// be better.
	firstInstructions *bytes.Buffer

	ConnCount int32
}

func NewSharedSession(tunnel Tunnel) (*SharedSession, error) {
	logrus.Debug("Connecting to tunnel")

	ss := &SharedSession{
		Tunnel:            tunnel,
		channels:          []chan []byte{},
		writeChannel:      make(chan []byte, 64),
		firstInstructions: new(bytes.Buffer),
	}

	go func() {
		<-time.After(time.Second)
		go ss.pumpFromGuac()
		go ss.pumpToGuac()
	}()

	return ss, nil
}

func (s *SharedSession) installChannel(channel chan []byte) {
	// put my channel into the list
	s.Lock()
	s.channels = append(s.channels, channel)
	s.Unlock()
}

func (s *SharedSession) uninstallChannel(channel chan []byte) {
	s.Lock()
	for i, c := range s.channels {
		if channel == c {
			s.channels = append(s.channels[:i], s.channels[i+1:]...)
		}
	}
	if len(s.channels) == 0 {
		s.Tunnel.Close()
		close(s.writeChannel)
	}
	s.Unlock()
}

// pumpFromGuac is the goroutine that pumps guac messages to all of the connected websockets
func (s *SharedSession) pumpFromGuac() {
	reader := s.Tunnel.AcquireReader()

	// if we leave this function close all channels since we lost connection to guacd
	defer func() {
		s.Lock()
		logrus.Debug("Lost connection to guacd")
		s.Tunnel.ReleaseReader()
		for _, c := range s.channels {
			close(c)
		}
		s.Unlock()
	}()

	var cursor int
	buffers := []*bytes.Buffer{
		bytes.NewBuffer(make([]byte, 0, maxGuacMessage*2)),
		bytes.NewBuffer(make([]byte, 0, maxGuacMessage*2)),
		bytes.NewBuffer(make([]byte, 0, maxGuacMessage*2)),
	}

	for {
		ins, err := reader.ReadSome()
		if err != nil {
			logrus.Error("Error reading from guacd", err)
			return
		}

		//str := string(ins)
		//if strings.HasPrefix(str, internalOpcodeIns) {
		//	// TODO Handle internal opcode from guac
		//	continue
		//}

		if s.firstInstructions.Len() < maxGuacMessage*24 {
			s.firstInstructions.Write(ins)
		}

		if _, err = buffers[cursor].Write(ins); err != nil {
			//out of memory?!
			logrus.Error("Failed to buffer guacd to ws")
			return
		}

		if !reader.Available() || buffers[cursor].Len() >= maxGuacMessage {
			s.RLock()
			for i := 0; i < len(s.channels); i++ {
				s.channels[i] <- buffers[cursor].Bytes()
			}
			s.RUnlock()
			cursor++
			if cursor >= len(buffers) {
				cursor = 0
			}
			buffers[cursor].Reset()
			reader.Flush()
		}
	}
}

// pumpToGuac pumps messages from the websockets to guacd
func (s *SharedSession) pumpToGuac() {
	writer := s.Tunnel.AcquireWriter()
	defer s.Tunnel.ReleaseWriter()
	defer s.Tunnel.Close()

	timer := time.NewTimer(SocketTimeout)
	var data []byte
	for {
		timer.Stop()
		timer.Reset(SocketTimeout)
		select {
		case <-timer.C:
			logrus.Debug("Closing tunnel due to socket timeout")
			return
		case data = <-s.writeChannel:
			if len(data) == 0 {
				return
			}
			str := string(data)

			if strings.HasPrefix(str, internalOpcodeIns) {
				// TODO handle custom ping (need to use InstructionReader)
				// messages starting with the InternalDataOpcode are never sent to guacd
				continue
			}

			if _, err := writer.Write(data); err != nil {
				logrus.Error("Failed writing to guacd", err)
				return
			}
		}
	}
}

func (s *SharedSession) Join(ws *websocket.Conn) {
	readChannel := make(chan []byte, 3)

	s.installChannel(readChannel)
	defer s.uninstallChannel(readChannel)

	//if err := ws.WriteMessage(1, []byte(NewInstruction(InternalDataOpcode, s.Tunnel.GetUUID().String()).String())); err != nil {
	//	logrus.Error("Error writing UUID", err)
	//	return
	//}

	if s.firstInstructions.Len() > 0 {
		if err := ws.WriteMessage(1, s.firstInstructions.Bytes()); err != nil {
			logrus.Error("Error writing first bytes", err)
			return
		}
	} else {
		logrus.Debugln("No initial data to send...")
	}

	go func() {
		for {
			_, data, err := ws.ReadMessage()
			if err != nil {
				logrus.Error("Error reading message from ws", err)
				return
			}
			// prevent a single client from disconnecting all clients
			// TODO send this when all clients disconnect
			if strings.HasPrefix(string(data), "10.disconnect") {
				continue
			}
			s.writeChannel <- data
		}
	}()

	for {
		ins := <-readChannel
		if err := ws.WriteMessage(1, ins); err != nil {
			logrus.Error("Failed sending message to ws", err)
			return
		}
	}
}
