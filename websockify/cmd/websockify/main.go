package main

import (
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"gitlab.com/isard/isardvdi/pkg/sdk"
)

var (
	apiAddr           string
	apiIgnoreCerts    = true
	apiProtocol       = "https"
	allowedHosts      []string
	allowedPortRanges []portRange
)

type portRange struct {
	min, max int
}

func init() {
	apiAddr = os.Getenv("API_DOMAIN")
	if apiAddr == "" || apiAddr == "isard-api" {
		apiAddr = "isard-api:5000"
		apiIgnoreCerts = false
		apiProtocol = "http"
	}

	// Initialize allowed hosts
	hostnames := os.Getenv("VIDEO_HYPERVISOR_HOSTNAMES")
	if hostnames == "" {
		allowedHosts = []string{"isard-hypervisor"}
	} else {
		allowedHosts = strings.Split(hostnames, ",")
		// Trim whitespace from each hostname
		for i, host := range allowedHosts {
			allowedHosts[i] = strings.TrimSpace(host)
		}
	}

	// Initialize allowed port ranges
	ports := os.Getenv("VIDEO_HYPERVISOR_PORTS")
	if ports == "" {
		ports = "5900-7899"
	}
	allowedPortRanges = parsePortRanges(ports)
}

// parsePortRanges parses port ranges like "5900-7899" or "5900-7899,8000-8999"
func parsePortRanges(portStr string) []portRange {
	var ranges []portRange
	parts := strings.Split(portStr, ",")

	for _, part := range parts {
		part = strings.TrimSpace(part)
		if strings.Contains(part, "-") {
			rangeParts := strings.Split(part, "-")
			if len(rangeParts) == 2 {
				min, err1 := strconv.Atoi(strings.TrimSpace(rangeParts[0]))
				max, err2 := strconv.Atoi(strings.TrimSpace(rangeParts[1]))
				if err1 == nil && err2 == nil {
					ranges = append(ranges, portRange{min: min, max: max})
				}
			}
		} else {
			// Single port
			port, err := strconv.Atoi(part)
			if err == nil {
				ranges = append(ranges, portRange{min: port, max: port})
			}
		}
	}

	return ranges
}

// isHostAllowed checks if the hostname is in the allowed list
func isHostAllowed(host string) bool {
	for _, allowedHost := range allowedHosts {
		if host == allowedHost {
			return true
		}
	}
	return false
}

// isPortAllowed checks if the port is within allowed ranges
func isPortAllowed(port int) bool {
	for _, portRange := range allowedPortRanges {
		if port >= portRange.min && port <= portRange.max {
			return true
		}
	}
	return false
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
	tkn := r.PathValue("token")
	if tkn == "" {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	port, err := strconv.Atoi(r.PathValue("port"))
	if err != nil {
		w.WriteHeader(http.StatusUnauthorized)
		return
	}

	hyper := r.PathValue("hyper")
	if hyper == "" {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	// Check if hypervisor host is allowed
	if !isHostAllowed(hyper) {
		log.Printf("hypervisor host not allowed: %s", hyper)
		w.WriteHeader(http.StatusForbidden)
		return
	}

	// Check if port is allowed
	if !isPortAllowed(port) {
		log.Printf("port not allowed: %d", port)
		w.WriteHeader(http.StatusForbidden)
		return
	}

	cli, err := sdk.NewClient(&sdk.Cfg{
		Host:        fmt.Sprintf("%s://%s", apiProtocol, apiAddr),
		IgnoreCerts: apiIgnoreCerts,
		Token:       tkn,
	})
	if err != nil {
		log.Printf("error creating the client: %v", err)
		w.WriteHeader(http.StatusInternalServerError)
		return
	}

	if err := cli.UserOwnsDesktop(r.Context(), &sdk.UserOwnsDesktopOpts{
		ProxyVideo:     r.Host,
		ProxyHyperHost: hyper,
		Port:           port,
	}); err != nil {
		if errors.Is(err, sdk.ErrForbidden) {
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

	tcpConn, err := net.Dial("tcp", net.JoinHostPort(hyper, strconv.Itoa(port)))
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
	http.HandleFunc("/conn-quality", connQuality)
	http.HandleFunc("/{hyper}/{port}/{token}", handler)

	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Fatalf("listen at port 8080: %v", err)
	}
}
