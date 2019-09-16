package guac

import (
	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
	"net/http"
	"sync"
	"sync/atomic"
)

type ConnectFunc func(*http.Request) (Tunnel, error)

type SharedWebsocketServer struct {
	// lock for sessions map
	sync.RWMutex
	// the function to connect to guac
	connect  ConnectFunc
	sessions map[string]*SharedSession
}

func NewSharedWebsocketServer(connect ConnectFunc) *SharedWebsocketServer {
	return &SharedWebsocketServer{
		connect:  connect,
		sessions: map[string]*SharedSession{},
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

	uuidParam := r.URL.Query().Get("uuid")

	var session *SharedSession
	if uuidParam == "" {
		tunnel, e := s.connect(r)
		if e != nil {
			return
		}
		session, err = NewSharedSession(tunnel)
		if err != nil {
			return
		}
		s.Lock()
		s.sessions[session.Tunnel.GetUUID()] = session
		s.Unlock()
	} else {
		s.RLock()
		session = s.sessions[uuidParam]
		s.RUnlock()
		if session == nil {
			logrus.Errorln("Session not found for UUID", uuidParam)
			return
		}
	}

	atomic.AddInt32(&session.ConnCount, 1)
	defer func() {
		v := atomic.AddInt32(&session.ConnCount, -1)
		if v == 0 {
			logrus.Debugln("All connections to tunnel has been closed, releasing session", session.Tunnel.GetUUID())
			s.Lock()
			delete(s.sessions, session.Tunnel.GetUUID())
			s.Unlock()
		}
	}()
	session.Join(ws)
}
