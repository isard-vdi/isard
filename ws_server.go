package guac

import (
	"bytes"
	"io"
	"net/http"

	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
)

type WebsocketServer struct {
	connect func(*http.Request) (Tunnel, error)
	OnConnect func(string, *http.Request)
	OnDisconnect func(string, *http.Request)
}

func NewWebsocketServer(connect func(*http.Request) (Tunnel, error)) *WebsocketServer {
	return &WebsocketServer{
		connect: connect,
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
	defer func() {
		if err = ws.Close(); err != nil {
			logrus.Errorln("Error closing websocket", err)
		}
	}()

	logrus.Debug("Connecting to tunnel")
	tunnel, e := s.connect(r)
	if e != nil {
		return
	}
	defer func() {
		if err = tunnel.Close(); err != nil {
			logrus.Errorln("Error closing tunnel", err)
		}
	}()
	logrus.Debug("Connected to tunnel")

	id := tunnel.ConnectionID()

	if s.OnConnect != nil {
		s.OnConnect(id, r)
	}
	if s.OnDisconnect != nil {
		defer s.OnDisconnect(id, r)
	}

	writer := tunnel.AcquireWriter()
	defer tunnel.ReleaseWriter()

	reader := tunnel.AcquireReader()
	defer tunnel.ReleaseReader()

	go wsToGuacd(ws, writer)
	guacdToWs(ws, reader)
}

type MessageReader interface {
	ReadMessage() (int, []byte, error)
}

func wsToGuacd(ws MessageReader, guacd io.Writer) {
	for {
		_, data, err := ws.ReadMessage()
		if err != nil {
			if err.Error() == "websocket: close 1005 (no status)" || err.Error() == "use of closed network connection" {
				return
			}
			logrus.Errorln("Error reading message from ws", err)
			return
		}

		if bytes.HasPrefix(data, internalOpcodeIns) {
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

func guacdToWs(ws MessageWriter, guacd InstructionReader) {
	buf := bytes.NewBuffer(make([]byte, 0, maxGuacMessage*2))

	for {
		ins, err := guacd.ReadSome()
		if err != nil {
			logrus.Errorln("Error reading from guacd", err)
			return
		}

		if bytes.HasPrefix(ins, internalOpcodeIns) {
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
				if err == websocket.ErrCloseSent {
					return
				}
				logrus.Errorln("Failed sending message to ws", err)
				return
			}
			buf.Reset()
		}
	}
}
