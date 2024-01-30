package guac

import (
	"bytes"
	"io"
	"net/http"

	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
)

// WebsocketServer implements a websocket-based connection to guacd.
type WebsocketServer struct {
	connect   func(*http.Request) (Tunnel, error)
	connectWs func(*websocket.Conn, *http.Request) (Tunnel, error)

	// OnConnect is an optional callback called when a websocket connects.
	// Deprecated: use OnConnectWs
	OnConnect func(string, *http.Request)
	// OnDisconnect is an optional callback called when the websocket disconnects.
	// Deprecated: use OnDisconnectWs
	OnDisconnect func(string, *http.Request, Tunnel)

	// OnConnectWs is an optional callback called when a websocket connects.
	OnConnectWs func(string, *websocket.Conn, *http.Request)
	// OnDisconnectWs is an optional callback called when the websocket disconnects.
	OnDisconnectWs func(string, *websocket.Conn, *http.Request, Tunnel)
}

// NewWebsocketServer creates a new server with a simple connect method.
func NewWebsocketServer(connect func(*http.Request) (Tunnel, error)) *WebsocketServer {
	return &WebsocketServer{
		connect: connect,
	}
}

// NewWebsocketServerWs creates a new server with a connect method that takes a websocket.
func NewWebsocketServerWs(connect func(*websocket.Conn, *http.Request) (Tunnel, error)) *WebsocketServer {
	return &WebsocketServer{
		connectWs: connect,
	}
}

const (
	websocketReadBufferSize  = MaxGuacMessage
	websocketWriteBufferSize = MaxGuacMessage * 2
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
			logrus.Traceln("Error closing websocket", err)
		}
	}()

	logrus.Debug("Connecting to tunnel")
	var tunnel Tunnel
	var e error
	if s.connect != nil {
		tunnel, e = s.connect(r)
	} else {
		tunnel, e = s.connectWs(ws, r)
	}
	if e != nil {
		return
	}
	defer func() {
		if err = tunnel.Close(); err != nil {
			logrus.Traceln("Error closing tunnel", err)
		}
	}()
	logrus.Debug("Connected to tunnel")

	id := tunnel.ConnectionID()

	if s.OnConnect != nil {
		s.OnConnect(id, r)
	}
	if s.OnConnectWs != nil {
		s.OnConnectWs(id, ws, r)
	}

	writer := tunnel.AcquireWriter()
	reader := tunnel.AcquireReader()

	if s.OnDisconnect != nil {
		defer s.OnDisconnect(id, r, tunnel)
	}
	if s.OnDisconnectWs != nil {
		defer s.OnDisconnectWs(id, ws, r, tunnel)
	}

	defer tunnel.ReleaseWriter()
	defer tunnel.ReleaseReader()

	go wsToGuacd(ws, writer)
	guacdToWs(ws, reader)
}

// MessageReader wraps a websocket connection and only permits Reading
type MessageReader interface {
	// ReadMessage should return a single complete message to send to guac
	ReadMessage() (int, []byte, error)
}

func wsToGuacd(ws MessageReader, guacd io.Writer) {
	for {
		_, data, err := ws.ReadMessage()
		if err != nil {
			logrus.Traceln("Error reading message from ws", err)
			return
		}

		if bytes.HasPrefix(data, internalOpcodeIns) {
			// messages starting with the InternalDataOpcode are never sent to guacd
			continue
		}

		if _, err = guacd.Write(data); err != nil {
			logrus.Traceln("Failed writing to guacd", err)
			return
		}
	}
}

// MessageWriter wraps a websocket connection and only permits Writing
type MessageWriter interface {
	// WriteMessage writes one or more complete guac commands to the websocket
	WriteMessage(int, []byte) error
}

func guacdToWs(ws MessageWriter, guacd InstructionReader) {
	buf := bytes.NewBuffer(make([]byte, 0, MaxGuacMessage*2))

	for {
		ins, err := guacd.ReadSome()
		if err != nil {
			logrus.Traceln("Error reading from guacd", err)
			return
		}

		if bytes.HasPrefix(ins, internalOpcodeIns) {
			// messages starting with the InternalDataOpcode are never sent to the websocket
			continue
		}

		if _, err = buf.Write(ins); err != nil {
			logrus.Traceln("Failed to buffer guacd to ws", err)
			return
		}

		// if the buffer has more data in it or we've reached the max buffer size, send the data and reset
		if !guacd.Available() || buf.Len() >= MaxGuacMessage {
			if err = ws.WriteMessage(1, buf.Bytes()); err != nil {
				if err == websocket.ErrCloseSent {
					return
				}
				logrus.Traceln("Failed sending message to ws", err)
				return
			}
			buf.Reset()
		}
	}
}
