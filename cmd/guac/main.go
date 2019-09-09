package main

import (
	"fmt"
	"github.com/jakecoffman/guac"
	"github.com/jakecoffman/guac/cmd/guac/secret"
	logger "github.com/sirupsen/logrus"
	"net/http"
)

func main() {
	logger.SetLevel(logger.DebugLevel)

	fs := http.FileServer(http.Dir("."))

	servlet := guac.NewHTTPTunnelServlet(DemoDoConnect)

	mux := http.NewServeMux()
	mux.Handle("/tunnel", servlet)
	mux.Handle("/tunnel/", servlet)
	mux.Handle("/", fs)

	logger.Println("Serving on http://127.0.0.1:4567")

	s := &http.Server{
		Addr:           ":4567",
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

	config.SetProtocol("ssh")
	config.SetParameter("port", "22")
	config.SetParameter("hostname", secret.Host)
	config.SetParameter("username", secret.Username)
	config.SetParameter("password", secret.Password)

	// view
	info.SetOptimalScreenHeight(600)
	info.SetOptimalScreenWidth(800)

	core, err := guac.NewInetSocket("127.0.0.1", 4822)
	if err != nil {
		return nil, err
	}
	socket, err := guac.NewConfiguredSocket3(&core, config, info)
	if err != nil {
		return nil, err
	}
	return guac.NewSimpleTunnel(&socket), nil
}
