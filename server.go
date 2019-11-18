package guac

import (
	"fmt"
	logger "github.com/sirupsen/logrus"
	"io"
	"net/http"
	"strings"
)

const (
	readPrefix        string = "read:"
	writePrefix       string = "write:"
	readPrefixLength         = len(readPrefix)
	writePrefixLength        = len(writePrefix)
	uuidLength               = 36
)

// Server uses HTTP requests to talk to guacd (as opposed to WebSockets in ws_server.go)
type Server struct {
	tunnels *TunnelMap
	connect func(*http.Request) (Tunnel, error)
}

// NewServer constructor
func NewServer(connect func(r *http.Request) (Tunnel, error)) *Server {
	return &Server{
		tunnels: NewTunnelMap(),
		connect: connect,
	}
}

// Registers the given tunnel such that future read/write requests to that tunnel will be properly directed.
func (s *Server) registerTunnel(tunnel Tunnel) {
	s.tunnels.Put(tunnel.GetUUID(), tunnel)
	logger.Debugf("Registered tunnel \"%v\".", tunnel.GetUUID())
}

// Deregisters the given tunnel such that future read/write requests to that tunnel will be rejected.
func (s *Server) deregisterTunnel(tunnel Tunnel) {
	s.tunnels.Remove(tunnel.GetUUID())
	logger.Debugf("Deregistered tunnel \"%v\".", tunnel.GetUUID())
}

// Returns the tunnel with the given UUID.
func (s *Server) getTunnel(tunnelUUID string) (ret Tunnel, err error) {
	var ok bool
	ret, ok = s.tunnels.Get(tunnelUUID)

	if !ok {
		err = ErrResourceNotFound.NewError("No such tunnel.")
	}
	return
}

func (s *Server) sendError(response http.ResponseWriter, guacStatus Status, message string) {
	response.Header().Set("Guacamole-Status-Code", fmt.Sprintf("%v", guacStatus.GetGuacamoleStatusCode()))
	response.Header().Set("Guacamole-Error-Message", message)
	response.WriteHeader(guacStatus.GetHTTPStatusCode())
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	err := s.handleTunnelRequestCore(w, r)
	if err == nil {
		return
	}
	guacErr := err.(*ErrGuac)
	switch guacErr.Kind {
	case ErrClient:
		logger.Warn("HTTP tunnel request rejected: ", err.Error())
		s.sendError(w, guacErr.Status, err.Error())
	default:
		logger.Error("HTTP tunnel request failed: ", err.Error())
		logger.Debug("Internal error in HTTP tunnel.", err)
		s.sendError(w, guacErr.Status, "Internal server error.")
	}
	return
}

func (s *Server) handleTunnelRequestCore(response http.ResponseWriter, request *http.Request) (err error) {
	query := request.URL.RawQuery
	if len(query) == 0 {
		return ErrClient.NewError("No query string provided.")
	}
	// If connect operation, call doConnect() and return tunnel UUID in response.
	if query == "connect" {
		tunnel, e := s.connect(request)

		// Failed to connect
		if e != nil {
			err = ErrResourceNotFound.NewError("No tunnel created.", e.Error())
			return
		}

		// Register newly-created tunnel
		s.registerTunnel(tunnel)

		// Ensure buggy browsers do not cache response
		response.Header().Set("Cache-Control", "no-cache")

		// Send UUID to client
		_, e = response.Write([]byte(tunnel.GetUUID()))

		if e != nil {
			err = ErrServer.NewError(e.Error())
			return
		}

	} else if strings.HasPrefix(query, readPrefix) {
		// If read operation, call doRead() with tunnel UUID, ignoring any
		// characters following the tunnel UUID.
		err = s.doRead(response, request, query[readPrefixLength:readPrefixLength+uuidLength])
	} else if strings.HasPrefix(query, writePrefix) {
		// If write operation, call doWrite() with tunnel UUID, ignoring any
		// characters following the tunnel UUID.
		err = s.doWrite(response, request, query[writePrefixLength:writePrefixLength+uuidLength])
	} else {
		// Otherwise, invalid operation
		err = ErrClient.NewError("Invalid tunnel operation: " + query)
	}

	return
}

// doRead takes guacd messages and sends them in the response
func (s *Server) doRead(response http.ResponseWriter, request *http.Request, tunnelUUID string) error {
	tunnel, err := s.getTunnel(tunnelUUID)
	if err != nil {
		return err
	}

	reader := tunnel.AcquireReader()
	defer tunnel.ReleaseReader()

	// Note that although we are sending text, Webkit browsers will
	// buffer 1024 bytes before starting a normal stream if we use
	// anything but application/octet-stream.
	response.Header().Set("Content-Type", "application/octet-stream")
	response.Header().Set("Cache-Control", "no-cache")

	if v, ok := response.(http.Flusher); ok {
		v.Flush()
	}

	err = s.writeSome(response, reader, tunnel)

	if err == nil {
		// success
		return err
	}

	switch err.(*ErrGuac).Kind {
	// Send end-of-stream marker and close tunnel if connection is closed
	case ErrConnectionClosed:
		// Deregister and close
		s.deregisterTunnel(tunnel)
		tunnel.Close()

		// End-of-instructions marker
		_, _ = response.Write([]byte("0.;"))
		if v, ok := response.(http.Flusher); ok {
			v.Flush()
		}
	default:
		logger.Debug("Error writing to servlet output stream", err)
		s.deregisterTunnel(tunnel)
		tunnel.Close()
	}

	return err
}

// writeSome drains the guacd buffer holding instructions into the response
func (s *Server) writeSome(response http.ResponseWriter, guacd InstructionReader, tunnel Tunnel) (err error) {
	var message []byte

	for {
		message, err = guacd.ReadSome()
		if err != nil {
			s.deregisterTunnel(tunnel)
			tunnel.Close()
			return
		}

		if len(message) == 0 {
			return
		}

		_, e := response.Write(message)
		if e != nil {
			err = ErrOther.NewError(e.Error())
			return
		}

		if !guacd.Available() {
			if v, ok := response.(http.Flusher); ok {
				v.Flush()
			}
		}

		// No more messages another guacd can take over
		if tunnel.HasQueuedReaderThreads() {
			break
		}
	}

	// End-of-instructions marker
	if _, err = response.Write([]byte("0.;")); err != nil {
		return err
	}
	if v, ok := response.(http.Flusher); ok {
		v.Flush()
	}
	return nil
}

// doWrite takes data from the request and sends it to guacd
func (s *Server) doWrite(response http.ResponseWriter, request *http.Request, tunnelUUID string) error {
	tunnel, err := s.getTunnel(tunnelUUID)
	if err != nil {
		return err
	}

	// We still need to set the content type to avoid the default of
	// text/html, as such a content type would cause some browsers to
	// attempt to parse the result, even though the JavaScript client
	// does not explicitly request such parsing.
	response.Header().Set("Content-Type", "application/octet-stream")
	response.Header().Set("Cache-Control", "no-cache")
	response.Header().Set("Content-Length", "0")

	writer := tunnel.AcquireWriter()
	defer tunnel.ReleaseWriter()

	_, err = io.Copy(writer, request.Body)

	if err != nil {
		s.deregisterTunnel(tunnel)
		if err = tunnel.Close(); err != nil {
			logger.Debug("Error closing tunnel")
		}
	}

	return err
}
