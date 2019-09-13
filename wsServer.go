package guac

import (
	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
	"net/http"
)

type WebsocketServer struct {
	connect func(*http.Request) (Tunnel, error)
}

func NewWebsocketServer(connect func(*http.Request) (Tunnel, error)) *WebsocketServer {
	return &WebsocketServer{
		connect: connect,
	}
}

const (
	websocketReadBufferSize  = 1024
	websocketWriteBufferSize = 16384
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
			logrus.Error("Error reading from guacd ", err)
			return
		}

		if err = ws.WriteMessage(1, ins); err != nil {
			logrus.Error("Failed sending message to ws", err)
			return
		}
	}
}
