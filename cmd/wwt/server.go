package main

import (
	"encoding/json"
	"errors"
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

	mux := http.NewServeMux()
	mux.Handle("/tunnel", servlet)
	mux.Handle("/tunnel/", servlet)
	mux.Handle("/websocket-tunnel", guac.NewSharedWebsocketServer(DemoDoConnect))
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
		Addr:           "127.0.0.1:4567",
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
	ip := getIP()
	if ip == "" {
		return nil, errors.New("failed to get IP")
	}
	config := guac.NewGuacamoleConfiguration()
	info := guac.NewGuacamoleClientInformation()

	config.Protocol = "rdp"
	config.Parameters = map[string]string{
		"port":     "3389",
		"hostname": ip,
		"username": "admin",
		"password": "WWTwwt1!",
		"security": "nla",
		"ignore-cert": "true",
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

func getIP() string {
	req, err := http.NewRequest("GET", "http://atc-access-api.apps-local.wwt.com/deployments?wwtUserId=46501", nil)
	if err != nil {
		logrus.Fatal(err)
	}
	req.Header.Add("remote_user", "coffmanj")

	res, err := http.DefaultClient.Do(req)
	if err != nil {
		logrus.Fatal(err)
	}
	defer res.Body.Close()

	var deployments []Deployment
	if err = json.NewDecoder(res.Body).Decode(&deployments); err != nil {
		logrus.Fatal(err)
	}

	if len(deployments) == 0 {
		return ""
	}

	return deployments[0].Accesses[0].Host
}

type Deployment struct {
	Accesses []Access `json:"accesses"`
}

type Access struct {
	Host string `json:"host"`
}
