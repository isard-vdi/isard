package main

import (
	"fmt"
	"github.com/jakecoffman/guac"
	"github.com/jakecoffman/guac/cmd/guac/secret"
	"github.com/sirupsen/logrus"
	"net/http"
	"net/http/pprof"
)

func main() {
	logrus.SetLevel(logrus.DebugLevel)

	fs := http.FileServer(http.Dir("."))

	servlet := guac.NewServer(DemoDoConnect)

	mux := http.NewServeMux()
	mux.Handle("/tunnel", servlet)
	mux.Handle("/tunnel/", servlet)
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
	config := guac.NewGuacamoleConfiguration()
	info := guac.NewGuacamoleClientInformation()

	config.Protocol = "ssh"
	config.Parameters = map[string]string{
		"port":     "22",
		"hostname": secret.Host,
		"username": secret.Username,
		"password": secret.Password,
	}

	//info.OptimalScreenHeight = 600
	//info.OptimalScreenWidth = 800
	info.AudioMimetypes = []string{"audio/L16", "rate=44100", "channels=2"}

	socket, err := guac.NewInetSocket("127.0.0.1", 4822)
	if err != nil {
		return nil, err
	}
	err = guac.ConfigureSocket(socket, config, info)
	if err != nil {
		return nil, err
	}
	return guac.NewSimpleTunnel(socket), nil
}
