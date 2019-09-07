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

	servlet := NewServletHandleStruct(DemoDoConnect)

	fs := http.FileServer(http.Dir("."))

	myHandler := http.NewServeMux()
	myHandler.HandleFunc("/tunnel", func(w http.ResponseWriter, r *http.Request) {
		logger.Println("1--", r.Method, r.URL)
		servlet.ServeHTTP(w, r)
	})
	myHandler.HandleFunc("/tunnel/", func(w http.ResponseWriter, r *http.Request) {
		logger.Println("2--", r.Method, r.URL)
		servlet.ServeHTTP(w, r)
	})
	myHandler.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		logger.Println(r.Method, r.URL)
		fs.ServeHTTP(w, r)
	})

	logger.Println("Serving on https://127.0.0.1:4567")
	// init server
	s := &http.Server{
		Addr:           ":4567",
		Handler:        myHandler,
		ReadTimeout:    guac.SocketTimeout,
		WriteTimeout:   guac.SocketTimeout,
		MaxHeaderBytes: 1 << 20,
	}
	err := s.ListenAndServe()
	if err != nil {
		fmt.Println(err)
	}
}

type BaseToHTTPServletResponseInterface struct {
	core     http.ResponseWriter
	commited bool
	err      error
}

// SwapResponse override
func SwapResponse(core http.ResponseWriter) guac.HTTPServletResponseInterface {
	return &BaseToHTTPServletResponseInterface{core: core}
}

// IsCommitted override
func (opt *BaseToHTTPServletResponseInterface) IsCommitted() (bool, error) {
	return opt.commited, opt.err
}

// AddHeader override
func (opt *BaseToHTTPServletResponseInterface) AddHeader(key, value string) {
	opt.core.Header().Add(key, value)
}

// SetHeader override
func (opt *BaseToHTTPServletResponseInterface) SetHeader(key, value string) {
	opt.core.Header().Set(key, value)
}

// SetContentType override
func (opt *BaseToHTTPServletResponseInterface) SetContentType(value string) {
	opt.core.Header().Set("Content-Type", value)
}

// SetContentLength override
func (opt *BaseToHTTPServletResponseInterface) SetContentLength(length int) {
	opt.core.Header().Set("Content-Length", fmt.Sprintf("%v", length))
}

// SendError override
func (opt *BaseToHTTPServletResponseInterface) SendError(sc int) error {
	opt.commited = true
	opt.core.WriteHeader(sc)
	return nil
}

// WriteString override
func (opt *BaseToHTTPServletResponseInterface) WriteString(data string) error {
	opt.commited = true
	opt.core.Write([]byte(data))
	return nil
}

// Write override
func (opt *BaseToHTTPServletResponseInterface) Write(data []byte) error {
	opt.commited = true
	opt.core.Write(data)
	return nil
}

// FlushBuffer override
func (opt *BaseToHTTPServletResponseInterface) FlushBuffer() error {
	if v, ok := opt.core.(http.Flusher); ok {
		v.Flush()
	}
	return nil
}

// Close override
func (opt *BaseToHTTPServletResponseInterface) Close() error {
	return opt.FlushBuffer()
}

// BaseToHTTPServletRequestInterface request
type BaseToHTTPServletRequestInterface struct {
	core *http.Request
}

// SwapRequest convert http.Request into Interface
func SwapRequest(core *http.Request) guac.HTTPServletRequestInterface {
	return &BaseToHTTPServletRequestInterface{core: core}
}

// GetQueryString override
func (opt *BaseToHTTPServletRequestInterface) GetQueryString() string {
	return opt.core.URL.RawQuery
}

// Read override
func (opt *BaseToHTTPServletRequestInterface) Read(buffer []byte) (int, error) {
	return opt.core.Body.Read(buffer)
}

const enterPath = "/tunnel"

// ServletHandleStruct servlet
type ServletHandleStruct struct {
	*guac.GuacamoleHTTPTunnelServlet
}

// NewServletHandleStruct servlet
func NewServletHandleStruct(doConnect guac.DoConnectInterface) *ServletHandleStruct {
	return &ServletHandleStruct{guac.NewGuacamoleHTTPTunnelServlet(doConnect)}
}

// GetEnterPath for http enter
func (opt *ServletHandleStruct) GetEnterPath() string {
	return enterPath
}

// ServeHTTP override
func (opt *ServletHandleStruct) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	var err error
	response := SwapResponse(w)
	request := SwapRequest(r)

	switch r.Method {
	case "GET":
		err = opt.DoGet(request, response)
	case "POST":
		err = opt.DoPost(request, response)
	}
	if err != nil {
		http.NotFound(w, r)
		return
	}
	return
}

// DemoDoConnect Demo & test code
func DemoDoConnect(request guac.HTTPServletRequestInterface) (ret guac.GuacamoleTunnel, err error) {
	config := guac.NewGuacamoleConfiguration()
	infomation := guac.NewGuacamoleClientInformation()

	config.SetProtocol("ssh")
	config.SetParameter("port", "22")
	config.SetParameter("hostname", secret.Host)
	config.SetParameter("username", secret.Username)
	config.SetParameter("password", secret.Password)

	// view
	infomation.SetOptimalScreenHeight(600)
	infomation.SetOptimalScreenWidth(800)

	core, err := guac.NewInetGuacamoleSocket("127.0.0.1", 4822)
	if err != nil {
		return
	}
	socket, err := guac.NewConfiguredGuacamoleSocket3(
		&core,
		config,
		infomation,
	)
	if err != nil {
		return
	}
	ret = guac.NewSimpleGuacamoleTunnel(&socket)
	return
}
