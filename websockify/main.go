package main

import (
	"log"
	"net"
	"net/http"
	"time"

	"github.com/gorilla/mux"
	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	Subprotocols:    []string{"binary"},
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

func handler(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)

	wsConn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("websocket upgrade: %v", err)
		return
	}

	defer wsConn.Close()

	tcpAddr := vars["hyper"] + ":" + vars["port"]
	tcpConn, err := net.Dial("tcp", tcpAddr)
	if err != nil {
		log.Printf("tcp connection: %v", err)
		return
	}
	defer tcpConn.Close()

	proxy(wsConn, tcpConn)
}

func proxy(wsConn *websocket.Conn, tcpConn net.Conn) {
	// WS -> TCP
	go func() {
		for {
			t, b, err := wsConn.ReadMessage()
			if err != nil {
				log.Printf("read ws message: %v", err)
				return
			}

			switch t {
			case websocket.BinaryMessage:
				_, err := tcpConn.Write(b)
				if err != nil {
					log.Printf("write tcp message: %v", err)
					return
				}

			case websocket.PingMessage:
				if err := wsConn.WriteMessage(websocket.PongMessage, b); err != nil {
					log.Printf("write ws pong: %v", err)
					return
				}
			case websocket.CloseMessage:
				return
			}
		}
	}()

	// TCP -> WS
	buf := make([]byte, 1024)
	for {
		n, err := tcpConn.Read(buf)
		if err != nil {
			log.Printf("read tcp message: %v", err)
			return
		}

		if err := wsConn.WriteMessage(websocket.BinaryMessage, buf[0:n]); err != nil {
			log.Printf("write ws message: %v", err)
			return
		}
	}
}

// taken from https://ankitbko.github.io/blog/2022/06/websocket-latency/
func connQuality(w http.ResponseWriter, r *http.Request) {
	wsConn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("websocket upgrade: %v", err)
		return
	}

	defer wsConn.Close()

	for {
		msg := map[string]interface{}{}
		if err := wsConn.ReadJSON(&msg); err != nil {
			log.Printf("read ws message: %v", err)
			return
		}

		t, ok := msg["type"]
		if ok {
			switch t {
			case "start":
				msg["server_ts"] = time.Now().UnixMicro()
			case "ack":
				msg["server_ack_ts"] = time.Now().UnixMicro()
			}

			if err := wsConn.WriteJSON(msg); err != nil {
				log.Printf("write ws message: %v", err)
				return
			}
		}
	}
}

func main() {
	r := mux.NewRouter()
	r.HandleFunc("/conn-quality", connQuality)
	r.HandleFunc("/{hyper}/{port:[0-9]+}", handler)

	http.Handle("/", r)
	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Fatalf("listen at port 8080: %v", err)
	}
}
