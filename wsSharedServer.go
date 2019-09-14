package guac

import (
	"bytes"
	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
	"net/http"
	"strings"
	"sync"
	"time"
)

type SharedWebsocketServer struct {
	// we need to lock around the channel map since there's asynchronous access to it
	sync.RWMutex
	// the function to connect to guac
	connect func(*http.Request) (Tunnel, error)
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
	firstInstructions [][]byte
}

func NewSharedWebsocketServer(connect func(*http.Request) (Tunnel, error)) *SharedWebsocketServer {
	return &SharedWebsocketServer{
		connect:           connect,
		channels:          []chan []byte{},
		writeChannel:      make(chan []byte, 64),
		firstInstructions: [][]byte{},
	}
}

func (s *SharedWebsocketServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	upgrader := websocket.Upgrader{
		ReadBufferSize:  websocketReadBufferSize,
		WriteBufferSize: websocketWriteBufferSize,
		CheckOrigin: func(r *http.Request) bool {
			return true // TODO
		},
	}
	protocol := r.Header.Get("Sec-Websocket-Protocol")
	ws, err := upgrader.Upgrade(w, r, http.Header{
		"Sec-Websocket-Protocol": {protocol},
	})
	if err != nil {
		logrus.Error("Failed to upgrade websocket", err)
		return
	}
	defer ws.Close()

	readChannel := make(chan []byte, 64)

	// I am first so create the tunnel
	if s.Tunnel == nil {
		logrus.Debug("Connecting to tunnel")
		var e error
		s.Tunnel, e = s.connect(r)
		if e != nil {
			return
		}

		reader := s.Tunnel.AcquireReader()
		if err := ws.WriteMessage(1, []byte(NewInstruction(InternalDataOpcode, s.Tunnel.GetUUID().String()).String())); err != nil {
			logrus.Error("Error writing UUID", err)
			return
		}

		s.installChannel(readChannel)
		defer s.uninstallChannel(readChannel)
		go s.guacToAllWs(reader)
		go s.allToGuacd()
	} else {
		if err := ws.WriteMessage(1, []byte(NewInstruction(InternalDataOpcode, s.Tunnel.GetUUID().String()).String())); err != nil {
			logrus.Error("Error writing UUID", err)
			return
		}
		if err := ws.WriteMessage(1, bytes.Join(s.firstInstructions, nil)); err != nil {
			logrus.Error("Error writing UUID", err)
			return
		}
		s.installChannel(readChannel)
		defer s.uninstallChannel(readChannel)
	}
	logrus.Debug("Connected to tunnel")

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
		if err = ws.WriteMessage(1, ins); err != nil {
			logrus.Error("Failed sending message to ws", err)
			return
		}
	}
}

func (s *SharedWebsocketServer) installChannel(channel chan []byte) {
	// put my channel into the list
	s.Lock()
	s.channels = append(s.channels, channel)
	s.Unlock()
}

func (s *SharedWebsocketServer) uninstallChannel(channel chan []byte) {
	s.Lock()
	for i, c := range s.channels {
		if channel == c {
			s.channels = append(s.channels[:i], s.channels[i+1:]...)
		}
	}
	if len(s.channels) == 0 {
		s.Tunnel.Close()
	}
	s.Unlock()
}

// guacToAllWs is the goroutine that pumps guac messages to all of the connected websockets
func (s *SharedWebsocketServer) guacToAllWs(reader *InstructionReader) {
	// if we leave this function close all channels since we lost connection to guacd
	defer func() {
		s.Lock()
		logrus.Debug("Lost connection to guacd")
		for _, c := range s.channels {
			close(c)
		}
		close(s.writeChannel)
		s.Unlock()
	}()

	for {
		ins, err := reader.ReadSome()
		if err != nil {
			logrus.Error("Error reading from guacd", err)
			return
		}

		if len(s.firstInstructions) < 768 {
			s.firstInstructions = append(s.firstInstructions, ins)
		}

		s.RLock()
		for i := 0; i < len(s.channels); i++ {
			s.channels[i] <- ins
		}
		reader.Flush()
		s.RUnlock()
	}
}

// allToGuacd pumps messages from the websockets to guacd
func (s *SharedWebsocketServer) allToGuacd() {
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
			logrus.Trace("TO:  ", string(data))
			if len(data) == 0 {
				return
			}
			if string(data[0]) == InternalDataOpcode {
				// TODO handle custom ping (need to use InstructionReader)
				logrus.Debug("Got opcode", string(data))

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
