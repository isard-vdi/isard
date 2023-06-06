package main

import (
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"time"

	"github.com/gorilla/mux"
	"github.com/gorilla/websocket"
	"gitlab.com/isard/isardvdi-cli/pkg/cfg"
	"gitlab.com/isard/isardvdi-cli/pkg/client"
)

var (
	apiAddr        string
	apiIgnoreCerts = true
	apiProtocol    = "https"
)

func init() {
	apiAddr = os.Getenv("API_DOMAIN")
	if apiAddr == "" || apiAddr == "isard-api" {
		apiAddr = "isard-api:5000"
		apiIgnoreCerts = false
		apiProtocol = "http"
	}
}

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
	tkn, err := url.QueryUnescape(vars["token"])
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	cli, err := client.NewClient(&cfg.Cfg{
		Host:        fmt.Sprintf("%s://%s", apiProtocol, apiAddr),
		IgnoreCerts: apiIgnoreCerts,
		Token:       tkn,
	})
	if err != nil {
		log.Printf("error creating the client: %v", err)
		w.WriteHeader(http.StatusInternalServerError)
		return
	}

	port, err := strconv.Atoi(vars["port"])
	if err != nil {
		w.WriteHeader(http.StatusUnauthorized)
		return
	}

	if err := cli.UserOwnsDesktop(r.Context(), &client.UserOwnsDesktopOpts{
		ProxyVideo:     r.Host,
		ProxyHyperHost: vars["hyper"],
		Port:           port,
	}); err != nil {
		if errors.Is(err, client.ErrForbidden) {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		log.Printf("unknown error: %v", err)
		w.WriteHeader(http.StatusInternalServerError)
		return
	}

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
	r.HandleFunc("/{hyper}/{port:[0-9]+}/{token}", handler)

	http.Handle("/", r)
	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Fatalf("listen at port 8080: %v", err)
	}
}
