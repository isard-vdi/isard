package guac

import (
	"bytes"
	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
	"io"
	"net/http"
	"strings"
	"sync"
)

type WebsocketServer struct {
	sync.RWMutex
	connect func(*http.Request) (Tunnel, error)
	connIds map[string]int
}

func NewWebsocketServer(connect func(*http.Request) (Tunnel, error)) *WebsocketServer {
	return &WebsocketServer{
		connect: connect,
		connIds: map[string]int{},
	}
}

const (
	websocketReadBufferSize  = maxGuacMessage
	websocketWriteBufferSize = maxGuacMessage * 2
)

func (s *WebsocketServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
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

	logrus.Debug("Connecting to tunnel")
	tunnel, e := s.connect(r)
	if e != nil {
		return
	}
	defer tunnel.Close()
	logrus.Debug("Connected to tunnel")

	id := tunnel.GetSocket().ID

	if _, ok := s.connIds[id]; !ok {
		s.Lock()
		s.connIds[id] = 1
		s.Unlock()
	} else {
		s.connIds[id]++
	}
	defer func() {
		s.Lock()
		numConns := s.connIds[id]
		if numConns <= 1 {
			delete(s.connIds, id)
		} else {
			numConns--
			s.connIds[id] = numConns
		}
		s.Unlock()
	}()

	writer := tunnel.AcquireWriter()
	defer tunnel.ReleaseWriter()

	reader := tunnel.AcquireReader()
	defer tunnel.ReleaseReader()

	// may need this for reconnect functionality
	//if err := ws.WriteMessage(1, []byte(NewInstruction(InternalDataOpcode, tunnel.GetUUID()).String())); err != nil {
	//	logrus.Error("Error writing UUID", err)
	//	return
	//}

	go wsToGuacd(ws, writer)
	guacdToWs(ws, reader)
}

func (s *WebsocketServer) Sessions() map[string]int {
	s.RLock()
	defer s.RUnlock()
	return s.connIds
}

type MessageReader interface {
	ReadMessage() (int, []byte, error)
}

func wsToGuacd(ws MessageReader, guacd io.Writer) {
	for {
		_, data, err := ws.ReadMessage()
		if err != nil {
			logrus.Errorln("Error reading message from ws", err)
			return
		}

		if strings.HasPrefix(string(data), internalOpcodeIns) {
			// TODO handle custom ping (need to use InstructionReader)

			// messages starting with the InternalDataOpcode are never sent to guacd
			continue
		}

		if _, err = guacd.Write(data); err != nil {
			logrus.Errorln("Failed writing to guacd", err)
			return
		}
	}
}

type MessageWriter interface {
	WriteMessage(int, []byte) error
}

func guacdToWs(ws MessageWriter, guacd *InstructionReader) {
	buf := bytes.NewBuffer(make([]byte, 0, maxGuacMessage*2))

	for {
		ins, err := guacd.ReadSome()
		if err != nil {
			logrus.Errorln("Error reading from guacd ", err)
			return
		}

		if strings.HasPrefix(string(ins), internalOpcodeIns) {
			// TODO handle custom ping (need to use InstructionReader)

			// messages starting with the InternalDataOpcode are never sent to guacd
			continue
		}

		if _, err = buf.Write(ins); err != nil {
			//out of memory?!
			logrus.Errorln("Failed to buffer guacd to ws")
			return
		}

		if !guacd.Available() || buf.Len() >= maxGuacMessage {
			if err = ws.WriteMessage(1, buf.Bytes()); err != nil {
				logrus.Errorln("Failed sending message to ws", err)
				return
			}
			buf.Reset()
		}
	}
}
