package main

import (
	"encoding/json"
	"fmt"
	"github.com/jakecoffman/guac"
	"github.com/sirupsen/logrus"
	"net/http"
	"net/http/pprof"
)

func main() {
	logrus.SetLevel(logrus.DebugLevel)

	fs := http.FileServer(http.Dir("."))

	servlet := guac.NewHTTPTunnelServlet(DemoDoConnect)
	wsServer := guac.NewSharedWebsocketServer(DemoDoConnect)

	mux := http.NewServeMux()
	mux.Handle("/tunnel", servlet)
	mux.Handle("/tunnel/", servlet)
	mux.Handle("/websocket-tunnel", wsServer)
	mux.HandleFunc("/sessions/", func(w http.ResponseWriter, r *http.Request) {
		sessionIds := wsServer.Sessions()
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(sessionIds); err != nil {
			logrus.Error(err)
		}
	})

	mux.Handle("/", fs)

	// Register pprof handlers
	mux.HandleFunc("/debug/pprof/", pprof.Index)
	mux.HandleFunc("/debug/pprof/cmdline", pprof.Cmdline)
	mux.HandleFunc("/debug/pprof/profile", pprof.Profile)
	mux.HandleFunc("/debug/pprof/symbol", pprof.Symbol)

	mux.Handle("/debug/pprof/goroutine", pprof.Handler("goroutine"))
	mux.Handle("/debug/pprof/heap", pprof.Handler("heap"))
	mux.Handle("/debug/pprof/threadcreate", pprof.Handler("threadcreate"))
	mux.Handle("/debug/pprof/block", pprof.Handler("block"))

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
	info := guac.NewGuacamoleClientInformation()

	config.Protocol = request.URL.Query().Get("scheme")
	config.Parameters = map[string]string{}
	for k, v := range request.URL.Query() {
		config.Parameters[k] = v[0]
	}

	//info.OptimalScreenHeight = 600
	//info.OptimalScreenWidth = 800
	info.AudioMimetypes = []string{"audio/L16", "rate=44100", "channels=2"}

	logrus.Debug("Connecting to guacd")
	socket, err := guac.NewInetSocket("127.0.0.1", 4822)
	if err != nil {
		return nil, err
	}
	logrus.Debug("Connected to guacd")
	err = guac.ConfigureSocket(socket, config, info)
	if err != nil {
		return nil, err
	}
	logrus.Debug("Socket configured")
	return guac.NewSimpleTunnel(socket), nil
}
