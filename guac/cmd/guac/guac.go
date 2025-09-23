package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"

	"github.com/sirupsen/logrus"
	"github.com/wwt/guac"
)

var (
	guacdAddr string
	apiAddr   string
)

func init() {
	guacdAddr = os.Getenv("GUACD_ADDR")
	if guacdAddr == "" {
		guacdAddr = "isard-vpn:4822"
	}

	apiAddr = os.Getenv("API_DOMAIN")
	if apiAddr == "" || apiAddr == "isard-api" {
		apiAddr = "isard-api:5000"
	} else {
		apiAddr = "https://" + apiAddr
	}
}

func isAuthenticated(handler http.Handler) http.HandlerFunc {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		logrus.Infof("****Authenticating request: %s %s", r.Method, r.URL.String())

		tkn := r.URL.Query().Get("session")
		if tkn == "" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		allowed, err := userOwnsDesktop(tkn, r.URL.Query().Get("hostname"))
		if err != nil {
			logrus.Errorf("error checking if user owns desktop: %v", err)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}

		if !allowed {
			logrus.Errorf("check if user owns desktop: %w", err)
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		handler.ServeHTTP(w, r)
	})
}

func userOwnsDesktop(tkn string, hostname string) (bool, error) {
	baseurl, err := url.Parse(fmt.Sprintf("http://%s", apiAddr))
	if err != nil {
		return false, fmt.Errorf("error parsing API URL: %v", err)
	}
	baseurl.Path = "/api/v3/"

	path, err := url.Parse("user/owns_desktop")
	if err != nil {
		return false, fmt.Errorf("error parsing relative API URL: %v", err)
	}

	rawBody := map[string]interface{}{}
	rawBody["ip"] = hostname
	url := baseurl.ResolveReference(path)
	body, err := json.Marshal(rawBody)
	if err != nil {
		return false, fmt.Errorf("error encoding body: %v", err)
	}
	buf := bytes.NewBuffer(body)
	req, err := http.NewRequest(http.MethodGet, url.String(), buf)
	if err != nil {
		return false, fmt.Errorf("error creating request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "isardvdi-guac")
	req.Header.Set("Authorization", "Bearer "+tkn)

	rsp, err := http.DefaultClient.Do(req)
	if err != nil {
		return false, fmt.Errorf("error performing request: %v", err)
	}
	defer rsp.Body.Close()

	switch {
	case rsp.StatusCode >= 500:
		return false, fmt.Errorf("API request failed with status: %s", rsp.Status)
	case rsp.StatusCode == 401 || rsp.StatusCode == 403:
		return false, nil
	case rsp.StatusCode >= 400:
		return false, fmt.Errorf("API request failed with status: %s", rsp.Status)
	default:
		return true, nil
	}
}

func logLevel() {
	levelStr := os.Getenv("LOG_LEVEL")
	if levelStr == "" {
		levelStr = "info"
	}

	if level, err := logrus.ParseLevel(levelStr); err != nil {
		logrus.Fatalf("Invalid LOG_LEVEL envrionment variable: %s", levelStr)
	} else {
		logrus.SetLevel(level)
		logrus.Infof("Log level set to %s", levelStr)
	}
}

type ServiceLogrusHook struct{}

func (h *ServiceLogrusHook) Levels() []logrus.Level {
	return logrus.AllLevels
}

func (h *ServiceLogrusHook) Fire(entry *logrus.Entry) error {
	entry.Data["service"] = "guac"
	return nil
}

func logFormat() {
	logrus.SetFormatter(&logrus.JSONFormatter{})
	logrus.AddHook(&ServiceLogrusHook{})
}

func main() {
	logFormat()
	logLevel()

	servlet := guac.NewServer(DemoDoConnect)
	wsServer := guac.NewWebsocketServer(DemoDoConnect)

	sessions := guac.NewMemorySessionStore()
	wsServer.OnConnect = sessions.Add
	wsServer.OnDisconnect = sessions.Delete

	mux := http.NewServeMux()
	mux.HandleFunc("/tunnel", isAuthenticated(servlet))
	mux.HandleFunc("/tunnel/", isAuthenticated(servlet))
	mux.HandleFunc("/websocket-tunnel", isAuthenticated(wsServer))
	mux.HandleFunc("/sessions/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		sessions.RLock()
		defer sessions.RUnlock()

		type ConnIds struct {
			Uuid string `json:"uuid"`
			Num  int    `json:"num"`
		}

		connIds := make([]*ConnIds, len(sessions.ConnIds))

		i := 0
		for id, num := range sessions.ConnIds {
			connIds[i] = &ConnIds{
				Uuid: id,
				Num:  num,
			}
		}

		if err := json.NewEncoder(w).Encode(connIds); err != nil {
			logrus.Error(err)
		}
	})

	logrus.Println("Serving on http://127.0.0.1:4567")

	s := &http.Server{
		Addr:           "0.0.0.0:4567",
		Handler:        mux,
		ReadTimeout:    guac.SocketTimeout,
		WriteTimeout:   guac.SocketTimeout,
		MaxHeaderBytes: 1 << 20,
	}
	err := s.ListenAndServe()
	if err != nil {
		fmt.Println(err)
	}
}

// DemoDoConnect creates the tunnel to the remote machine (via guacd)
func DemoDoConnect(request *http.Request) (guac.Tunnel, error) {
	config := guac.NewGuacamoleConfiguration()

	var query url.Values
	if request.URL.RawQuery == "connect" {
		// http tunnel uses the body to pass parameters
		data, err := ioutil.ReadAll(request.Body)
		if err != nil {
			logrus.Errorf("Failed to read body ", err)
			return nil, err
		}
		_ = request.Body.Close()
		queryString := string(data)
		query, err = url.ParseQuery(queryString)
		if err != nil {
			logrus.Errorf("Failed to parse body query ", err)
			return nil, err
		}
		logrus.Debugln("body:", queryString, query)
	} else {
		query = request.URL.Query()
	}

	config.Protocol = query.Get("scheme")
	config.Parameters = map[string]string{}
	for k, v := range query {
		config.Parameters[k] = v[0]
	}

	var err error
	if query.Get("width") != "" {
		config.OptimalScreenHeight, err = strconv.Atoi(query.Get("width"))
		if err != nil || config.OptimalScreenHeight == 0 {
			logrus.Error("Invalid height")
			config.OptimalScreenHeight = 600
		}
	}
	if query.Get("height") != "" {
		config.OptimalScreenWidth, err = strconv.Atoi(query.Get("height"))
		if err != nil || config.OptimalScreenWidth == 0 {
			logrus.Error("Invalid width")
			config.OptimalScreenWidth = 800
		}
	}
	config.AudioMimetypes = []string{"audio/L16", "rate=44100", "channels=2"}

	logrus.Debug("Connecting to guacd")
	addr, err := net.ResolveTCPAddr("tcp", guacdAddr)
	if err != nil {
		logrus.Errorf("resolve guacd address: %v", err)
		return nil, err
	}

	conn, err := net.DialTCP("tcp", nil, addr)
	if err != nil {
		logrus.Errorf("error while connecting to guacd", err)
		return nil, err
	}

	stream := guac.NewStream(conn, guac.SocketTimeout)

	logrus.Debug("Connected to guacd")
	if request.URL.Query().Get("uuid") != "" {
		config.ConnectionID = request.URL.Query().Get("uuid")
	}
	logrus.Debugf("Starting handshake with %+v", config)
	err = stream.Handshake(config)
	if err != nil {
		return nil, err
	}
	logrus.Debug("Socket configured")
	return guac.NewSimpleTunnel(stream), nil
}
