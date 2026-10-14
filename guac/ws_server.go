package guac

import (
	"bytes"
	"io"
	"net/http"
	"strconv"

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
	// OnOutcome is an optional callback called once per connection with how reaching the remote desktop went.
	OnOutcome func(*http.Request, Outcome)
}

// Outcome is how a connection to the remote desktop ended up: connected, or the first error guacd reported.
type Outcome struct {
	Connected bool
	Code      int
	Message   string
}

var (
	defaultLayerSizeIns = []byte("4.size,1.0,")
	errorIns            = []byte("5.error,")
)

// outcomeOf tells whether an instruction from guacd settles the outcome: the default layer only gets a size
// once the remote session exists, while the client's connected state arrives before guacd has negotiated anything.
func outcomeOf(ins []byte) (Outcome, bool) {
	if bytes.HasPrefix(ins, defaultLayerSizeIns) {
		return Outcome{Connected: true}, true
	}
	if !bytes.HasPrefix(ins, errorIns) {
		return Outcome{}, false
	}
	parsed, err := Parse(ins)
	if err != nil || len(parsed.Args) < 2 {
		return Outcome{}, true
	}
	code, _ := strconv.Atoi(parsed.Args[1])
	return Outcome{Code: code, Message: parsed.Args[0]}, true
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

	var outcome func(Outcome)
	if s.OnOutcome != nil {
		outcome = func(o Outcome) { s.OnOutcome(r, o) }
	}

	go wsToGuacd(ws, writer)
	guacdToWs(ws, reader, outcome)
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

func guacdToWs(ws MessageWriter, guacd InstructionReader, outcome func(Outcome)) {
	buf := bytes.NewBuffer(make([]byte, 0, MaxGuacMessage*2))

	for {
		ins, err := guacd.ReadSome()
		if err != nil {
			logrus.Traceln("Error reading from guacd", err)
			return
		}

		if outcome != nil {
			if o, settled := outcomeOf(ins); settled {
				outcome(o)
				outcome = nil
			}
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
