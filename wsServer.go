package guac

import (
	"bytes"
	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
	"log"
	"net/http"
	"sync"
)

type WebsocketServer struct {
	connect func(*http.Request) (Tunnel, error)
}

func NewWebsocketServer(connect func(*http.Request) (Tunnel, error)) *WebsocketServer {
	return &WebsocketServer{
		connect: connect,
	}
}

func (s *WebsocketServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	upgrader := websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
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

	logrus.Debug("Connecting to tunnel")
	tunnel, e := s.connect(r)
	if e != nil {
		return
	}
	defer tunnel.Close()
	logrus.Debug("Connected to tunnel")

	go wsToGuacd(ws, tunnel)
	guacdToWs(tunnel, ws)
}

func wsToGuacd(ws *websocket.Conn, tunnel Tunnel) {
	writer := tunnel.AcquireWriter()
	defer tunnel.ReleaseWriter()
	defer tunnel.Close()

	for {
		_, data, err := ws.ReadMessage()
		if err != nil {
			logrus.Error("Error reading message from ws", err)
			return
		}

		if string(data[0]) == InternalDataOpcode {
			// TODO handle custom ping (need to use InstructionReader)
			logrus.Debug("Got opcode", string(data))

			// messages starting with the InternalDataOpcode are never sent to guacd
			continue
		}

		if _, err = writer.Write(data); err != nil {
			logrus.Error("Failed writing to guacd", err)
			return
		}
	}
}

func guacdToWs(tunnel Tunnel, ws *websocket.Conn) {
	reader := tunnel.AcquireReader()
	if err := ws.WriteMessage(1, []byte(NewInstruction(InternalDataOpcode, tunnel.GetUUID().String()).String())); err != nil {
		logrus.Error("Error writing UUID", err)
		return
	}

	for {
		ins, err := reader.ReadSome()
		if err != nil {
			logrus.Error("Error reading from guacd", err)
			return
		}

		if err = ws.WriteMessage(1, ins); err != nil {
			logrus.Error("Failed sending message to ws", err)
			return
		}
	}
}

type SharedWebsocketServer struct {
	sync.RWMutex
	connect func(*http.Request) (Tunnel, error)
	Tunnel
	channels          []chan []byte
	firstInstructions [][]byte
}

func NewSharedWebsocketServer(connect func(*http.Request) (Tunnel, error)) *SharedWebsocketServer {
	return &SharedWebsocketServer{
		connect:           connect,
		channels:          []chan []byte{},
		firstInstructions: [][]byte{},
	}
}

func (s *SharedWebsocketServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	upgrader := websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
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

	channel := make(chan []byte, 64)

	// I am first so create the tunnel
	if s.Tunnel == nil {
		logrus.Debug("Connecting to tunnel")
		var e error
		s.Tunnel, e = s.connect(r)
		if e != nil {
			return
		}
		defer func() {
			if !s.Tunnel.HasQueuedReaderThreads() && !s.Tunnel.HasQueuedWriterThreads() {
				s.Tunnel.Close()
			}
		}()

		reader := s.Tunnel.AcquireReader()
		if err := ws.WriteMessage(1, []byte(NewInstruction(InternalDataOpcode, s.Tunnel.GetUUID().String()).String())); err != nil {
			logrus.Error("Error writing UUID", err)
			return
		}

		s.installWs(channel)
		defer s.uninstallWs(channel)
		go s.guacToAllWs(reader)
		go wsToGuacd(ws, s.Tunnel)
	} else {
		go func() {
			for {
				// throw away inputs...
				_, _, err := ws.ReadMessage()
				if err != nil {
					logrus.Error("Error reading message from ws (trashed)", err)
					return
				}
			}
		}()
		if err := ws.WriteMessage(1, []byte(NewInstruction(InternalDataOpcode, s.Tunnel.GetUUID().String()).String())); err != nil {
			logrus.Error("Error writing UUID", err)
			return
		}
		if err := ws.WriteMessage(1, bytes.Join(s.firstInstructions, nil)); err != nil {
			logrus.Error("Error writing UUID", err)
			return
		}
		s.installWs(channel)
		defer s.uninstallWs(channel)
	}
	logrus.Debug("Connected to tunnel")

	for {
		ins := <-channel
		if err = ws.WriteMessage(1, ins); err != nil {
			logrus.Error("Failed sending message to ws", err)
			return
		}
	}
}

func (s *SharedWebsocketServer) installWs(channel chan []byte) {
	// put my channel into the list
	s.Lock()
	s.channels = append(s.channels, channel)
	log.Println("Added channel")
	s.Unlock()
}

func (s *SharedWebsocketServer) uninstallWs(channel chan []byte) {
	s.Lock()
	for i, c := range s.channels {
		if channel == c {
			s.channels = append(s.channels[:i], s.channels[i+1:]...)
		}
	}
	log.Println("Removed channel")
	if len(s.channels) == 0 {
		s.Tunnel.Close()
	}
	s.Unlock()
}

func (s *SharedWebsocketServer) guacToAllWs(reader *InstructionReader) {
	for {
		ins, err := reader.ReadSome()
		if err != nil {
			logrus.Error("Error reading from guacd", err)
			return
		}

		if len(s.firstInstructions) < 768 {
			log.Println(string(ins))
			s.firstInstructions = append(s.firstInstructions, ins)
		}

		s.RLock()
		for i := 0; i < len(s.channels); i++ {
			// to do, if the channel fills up this will error?
			s.channels[i] <- ins
		}
		s.RUnlock()
	}
}
