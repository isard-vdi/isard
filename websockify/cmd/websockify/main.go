package main

import (
	"errors"
	"fmt"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/pkg/sdk"
)

var (
	logger            *zerolog.Logger
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
	// Initialize logger first
	logLevel := strings.ToUpper(os.Getenv("LOG_LEVEL"))
	if logLevel == "" {
		logLevel = "INFO"
	}

	logger = log.New("websockify", logLevel)

	logger.Info().Str("log_level", logLevel).Msg("Starting websockify service")

	apiAddr = os.Getenv("API_DOMAIN")
	if apiAddr == "" || apiAddr == "isard-api" {
		apiAddr = "isard-api:5000"
		apiIgnoreCerts = false
		apiProtocol = "http"
		logger.Info().Str("api_addr", apiAddr).Msg("Using internal API")
	} else {
		logger.Info().Str("api_addr", apiAddr).Msg("Using external API")
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
	logger.Info().Interface("allowed_hosts", allowedHosts).Msg("Allowed hypervisor hosts")

	// Initialize allowed port ranges
	ports := os.Getenv("VIDEO_HYPERVISOR_PORTS")
	if ports == "" {
		ports = "5900-7899"
	}
	allowedPortRanges = parsePortRanges(ports)
	logger.Info().Interface("allowed_port_ranges", allowedPortRanges).Msg("Allowed port ranges")
}

// parsePortRanges parses port ranges like "5900-7899" or "5900-7899,8000-8999"
func parsePortRanges(portStr string) []portRange {
	var ranges []portRange
	logger.Debug().Str("port_string", portStr).Msg("Parsing port ranges")

	parts := strings.Split(portStr, ",")
	logger.Debug().Strs("parts", parts).Msg("Split port string into parts")

	for _, part := range parts {
		part = strings.TrimSpace(part)
		if strings.Contains(part, "-") {
			rangeParts := strings.Split(part, "-")
			if len(rangeParts) == 2 {
				min, err1 := strconv.Atoi(strings.TrimSpace(rangeParts[0]))
				max, err2 := strconv.Atoi(strings.TrimSpace(rangeParts[1]))
				if err1 == nil && err2 == nil {
					ranges = append(ranges, portRange{min: min, max: max})
				} else {
					logger.Warn().Str("part", part).Msg("Invalid port range format")
				}
			}
		} else {
			// Single port
			port, err := strconv.Atoi(part)
			if err == nil {
				ranges = append(ranges, portRange{min: port, max: port})
			} else {
				logger.Warn().Str("part", part).Msg("Invalid port format")
			}
		}
	}

	return ranges
}

// isHostAllowed checks if the hostname is in the allowed list
func isHostAllowed(host string) bool {
	for _, allowedHost := range allowedHosts {
		if host == allowedHost {
			logger.Debug().Str("host", host).Msg("Host is allowed")
			return true
		}
	}
	logger.Debug().Str("host", host).Interface("allowed_hosts", allowedHosts).Msg("Host is not in allowed list")
	return false
}

// isPortAllowed checks if the port is within allowed ranges
func isPortAllowed(port int) bool {
	logger.Debug().Int("port", port).Int("allowed_ranges_count", len(allowedPortRanges)).Msg("Checking if port is allowed")

	if len(allowedPortRanges) == 0 {
		logger.Debug().Int("port", port).Msg("No allowed port ranges configured - denying access")
		return false
	}

	for _, portRange := range allowedPortRanges {
		if port >= portRange.min && port <= portRange.max {
			logger.Debug().Int("port", port).Int("min", portRange.min).Int("max", portRange.max).Msg("Port is allowed")
			return true
		}
	}
	logger.Debug().Int("port", port).Interface("allowed_port_ranges", allowedPortRanges).Msg("Port is not in allowed ranges")
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
	clientIP := r.Header.Get("X-Forwarded-For")
	if clientIP == "" {
		clientIP = r.RemoteAddr
	}

	tkn := r.PathValue("token")
	if tkn == "" {
		logger.Warn().Str("client_ip", clientIP).Msg("Bad request: missing token")
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	port, err := strconv.Atoi(r.PathValue("port"))
	if err != nil {
		logger.Warn().Str("client_ip", clientIP).Str("port", r.PathValue("port")).Msg("Bad request: invalid port")
		w.WriteHeader(http.StatusUnauthorized)
		return
	}

	hyper := r.PathValue("hyper")
	if hyper == "" {
		logger.Warn().Str("client_ip", clientIP).Msg("Bad request: missing hypervisor")
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	logger.Info().Str("client_ip", clientIP).Str("hypervisor", hyper).Int("port", port).Msg("WebSocket connection request")

	// Check if hypervisor host is allowed
	if !isHostAllowed(hyper) {
		logger.Warn().Str("hypervisor", hyper).Str("client_ip", clientIP).Msg("Forbidden: hypervisor host not allowed")
		w.WriteHeader(http.StatusForbidden)
		return
	}

	// Check if port is allowed
	if !isPortAllowed(port) {
		logger.Warn().Int("port", port).Str("client_ip", clientIP).Msg("Forbidden: port not allowed")
		w.WriteHeader(http.StatusForbidden)
		return
	}

	cli, err := sdk.NewClient(&sdk.Cfg{
		Host:        fmt.Sprintf("%s://%s", apiProtocol, apiAddr),
		IgnoreCerts: apiIgnoreCerts,
		Token:       tkn,
	})
	if err != nil {
		logger.Error().Err(err).Str("hypervisor", hyper).Int("port", port).Str("client_ip", clientIP).Msg("Error creating API client")
		w.WriteHeader(http.StatusInternalServerError)
		return
	}

	logger.Debug().Str("hypervisor", hyper).Int("port", port).Str("client_ip", clientIP).Msg("Validating user ownership")
	if err := cli.UserOwnsDesktop(r.Context(), &sdk.UserOwnsDesktopOpts{
		ProxyVideo:     r.Host,
		ProxyHyperHost: hyper,
		Port:           port,
	}); err != nil {
		if errors.Is(err, sdk.ErrForbidden) {
			logger.Warn().Str("hypervisor", hyper).Int("port", port).Str("client_ip", clientIP).Msg("Unauthorized: user does not own desktop")
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		logger.Error().Err(err).Str("hypervisor", hyper).Int("port", port).Str("client_ip", clientIP).Msg("API validation error")
		w.WriteHeader(http.StatusInternalServerError)
		return
	}

	logger.Debug().Str("hypervisor", hyper).Int("port", port).Str("client_ip", clientIP).Msg("User validation successful, upgrading to WebSocket")
	wsConn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		logger.Error().Err(err).Str("hypervisor", hyper).Int("port", port).Str("client_ip", clientIP).Msg("WebSocket upgrade failed")
		return
	}

	defer wsConn.Close()

	logger.Debug().Str("hypervisor", hyper).Int("port", port).Msg("Establishing TCP connection")
	tcpConn, err := net.Dial("tcp", net.JoinHostPort(hyper, strconv.Itoa(port)))
	if err != nil {
		logger.Error().Err(err).Str("hypervisor", hyper).Int("port", port).Str("client_ip", clientIP).Msg("TCP connection failed")
		return
	}
	defer tcpConn.Close()

	logger.Info().Str("client_ip", clientIP).Str("hypervisor", hyper).Int("port", port).Msg("WebSocket proxy established")
	proxy(wsConn, tcpConn, fmt.Sprintf("%s:%d", hyper, port), clientIP)
}

func proxy(wsConn *websocket.Conn, tcpConn net.Conn, target string, clientIP string) {
	connectionStart := time.Now()
	var totalBytesWsToTcp, totalBytesTcpToWs int64
	var packetCountWsToTcp, packetCountTcpToWs int64

	logger.Debug().Str("client_ip", clientIP).Str("target", target).Msg("Starting proxy session")

	// WS -> TCP
	go func() {
		defer func() {
			wsConn.Close()
			tcpConn.Close()
		}()

		for {
			t, b, err := wsConn.ReadMessage()
			if err != nil {
				if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
					logger.Warn().Err(err).Str("client_ip", clientIP).Str("target", target).Msg("WebSocket read error")
				} else {
					logger.Debug().Str("client_ip", clientIP).Str("target", target).Msg("WebSocket connection closed")
				}
				return
			}

			switch t {
			case websocket.BinaryMessage:
				_, err := tcpConn.Write(b)
				if err != nil {
					logger.Warn().Err(err).Str("client_ip", clientIP).Str("target", target).Msg("TCP write error")
					return
				}
				atomic.AddInt64(&totalBytesWsToTcp, int64(len(b)))
				atomic.AddInt64(&packetCountWsToTcp, 1)
				// Only log large packets or every 100 packets to reduce noise
				if len(b) > 4096 {
					logger.Debug().Int("bytes", len(b)).Str("client_ip", clientIP).Str("target", target).Msg("WS->TCP large packet")
				}

			case websocket.PingMessage:
				if err := wsConn.WriteMessage(websocket.PongMessage, b); err != nil {
					logger.Warn().Err(err).Str("client_ip", clientIP).Str("target", target).Msg("WebSocket pong error")
					return
				}
				// Only log ping/pong in trace level if needed
			case websocket.CloseMessage:
				logger.Debug().Str("client_ip", clientIP).Str("target", target).Msg("WebSocket close message received")
				return
			}
		}
	}()

	// TCP -> WS
	defer func() {
		duration := time.Since(connectionStart)
		logger.Info().
			Str("client_ip", clientIP).
			Str("target", target).
			Dur("duration", duration).
			Int64("ws_to_tcp_bytes", totalBytesWsToTcp).
			Int64("tcp_to_ws_bytes", totalBytesTcpToWs).
			Msg("Proxy session ended")
	}()

	buf := make([]byte, 1024)
	for {
		n, err := tcpConn.Read(buf)
		if err != nil {
			logger.Debug().Err(err).Str("client_ip", clientIP).Str("target", target).Msg("TCP read ended")
			return
		}

		if err := wsConn.WriteMessage(websocket.BinaryMessage, buf[0:n]); err != nil {
			logger.Warn().Err(err).Str("client_ip", clientIP).Str("target", target).Msg("WebSocket write error")
			return
		}
		atomic.AddInt64(&totalBytesTcpToWs, int64(n))
		atomic.AddInt64(&packetCountTcpToWs, 1)
		// Only log large packets to reduce noise
		if n > 4096 {
			logger.Debug().Int("bytes", n).Str("client_ip", clientIP).Str("target", target).Msg("TCP->WS large packet")
		}
	}
}

// taken from https://ankitbko.github.io/blog/2022/06/websocket-latency/
func connQuality(w http.ResponseWriter, r *http.Request) {
	clientIP := r.Header.Get("X-Forwarded-For")
	if clientIP == "" {
		clientIP = r.RemoteAddr
	}

	logger.Info().Str("client_ip", clientIP).Msg("Connection quality test requested")

	wsConn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		logger.Error().Err(err).Str("client_ip", clientIP).Msg("WebSocket upgrade failed for connection quality test")
		return
	}

	defer wsConn.Close()
	logger.Debug().Str("client_ip", clientIP).Msg("Connection quality test WebSocket established")

	for {
		msg := map[string]interface{}{}
		if err := wsConn.ReadJSON(&msg); err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				logger.Warn().Err(err).Str("client_ip", clientIP).Msg("Connection quality test read error")
			} else {
				logger.Debug().Str("client_ip", clientIP).Msg("Connection quality test ended")
			}
			return
		}

		t, ok := msg["type"]
		if ok {
			switch t {
			case "start":
				msg["server_ts"] = time.Now().UnixMicro()
				logger.Debug().Str("client_ip", clientIP).Msg("Connection quality start message")
			case "ack":
				msg["server_ack_ts"] = time.Now().UnixMicro()
				logger.Debug().Str("client_ip", clientIP).Msg("Connection quality ack message")
			}

			if err := wsConn.WriteJSON(msg); err != nil {
				logger.Warn().Err(err).Str("client_ip", clientIP).Msg("Connection quality test write error")
				return
			}
		}
	}
}

func main() {
	logger.Info().Msg("Starting websockify server on :8080")

	http.HandleFunc("/conn-quality", connQuality)
	http.HandleFunc("/{hyper}/{port}/{token}", handler)

	logger.Info().Msg("Websockify server listening on :8080")
	if err := http.ListenAndServe(":8080", nil); err != nil {
		logger.Fatal().Err(err).Msg("Failed to start server on port 8080")
	}
}
