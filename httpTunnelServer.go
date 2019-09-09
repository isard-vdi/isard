package guac

import (
	"fmt"
	logger "github.com/sirupsen/logrus"
	"io"
	"net/http"
	"strings"
)

/**
 * Logger for this class.
 */
//private final Logger logger = LoggerFactory.getLogger(HttpTunnelServlet.class);

const (
	/*READ_PREFIX *
	 * The prefix of the query string which denotes a tunnel read operation.
	 */
	ReadPrefix string = "read:"

	/*WRITE_PREFIX *
	 * The prefix of the query string which denotes a tunnel write operation.
	 */
	WritePrefix string = "write:"

	/*READ_PREFIX_LENGTH *
	 * The length of the read prefix, in characters.
	 */
	ReadPrefixLength = len(ReadPrefix)

	/*WRITE_PREFIX_LENGTH *
	 * The length of the write prefix, in characters.
	 */
	WritePrefixLength = len(WritePrefix)

	/*UUID_LENGTH *
	 * The length of every tunnel UUID, in characters.
	 */
	UuidLength = 36
)

/*HttpTunnelServlet ==> HttpServlet*
 * A HttpServlet implementing and abstracting the operations required by the
 * HTTP implementation of the JavaScript Guacamole client's tunnel.
 */
type HttpTunnelServlet struct {
	/**
	 * Map of absolutely all active tunnels using HTTP, indexed by tunnel UUID.
	 */
	tunnels HttpTunnelMap
	connect func(*http.Request) (Tunnel, error)
}

// NewHTTPTunnelServlet Construct function
func NewHTTPTunnelServlet(connect func(r *http.Request) (Tunnel, error)) *HttpTunnelServlet {
	return &HttpTunnelServlet{
		tunnels: NewHttpTunnelMap(),
		connect: connect,
	}
}

/**
 * Registers the given tunnel such that future read/write requests to that
 * tunnel will be properly directed.
 *
 * @param tunnel
 *     The tunnel to register.
 */
func (s *HttpTunnelServlet) registerTunnel(tunnel Tunnel) {
	s.tunnels.Put(tunnel.GetUUID().String(), tunnel)
	logger.Debugf("Registered tunnel \"%v\".", tunnel.GetUUID())
}

/**
 * Deregisters the given tunnel such that future read/write requests to
 * that tunnel will be rejected.
 *
 * @param tunnel
 *     The tunnel to deregister.
 */
func (s *HttpTunnelServlet) deregisterTunnel(tunnel Tunnel) {
	s.tunnels.Remove(tunnel.GetUUID().String())
	logger.Debugf("Deregistered tunnel \"%v\".", tunnel.GetUUID())
}

/**
 * Returns the tunnel with the given UUID, if it has been registered with
 * registerTunnel() and not yet deregistered with deregisterTunnel().
 */
func (s *HttpTunnelServlet) getTunnel(tunnelUUID string) (ret Tunnel, err error) {
	var ok bool
	ret, ok = s.tunnels.Get(tunnelUUID)

	if !ok {
		err = ErrResourceNotFound.NewError("No such tunnel.")
	}
	return
}

func (s *HttpTunnelServlet) sendError(response http.ResponseWriter, guacStatus Status, message string) {
	response.Header().Set("Guacamole-Status-Code", fmt.Sprintf("%v", guacStatus.GetGuacamoleStatusCode()))
	response.Header().Set("Guacamole-Error-Message", message)
	response.WriteHeader(guacStatus.GetHTTPStatusCode())
}

func (s *HttpTunnelServlet) ServeHTTP(w http.ResponseWriter, r *http.Request) {
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

func (s *HttpTunnelServlet) handleTunnelRequestCore(response http.ResponseWriter, request *http.Request) (err error) {
	query := request.URL.RawQuery
	if len(query) == 0 {
		return ErrClient.NewError("No query string provided.")
	}
	// If connect operation, call doConnect() and return tunnel UUID
	// in response.
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
		_, e = response.Write([]byte(tunnel.GetUUID().String()))

		if e != nil {
			err = ErrServer.NewError(e.Error())
			return
		}

	} else if strings.HasPrefix(query, ReadPrefix) {
		// If read operation, call doRead() with tunnel UUID, ignoring any
		// characters following the tunnel UUID.
		err = s.doRead(response, request, query[ReadPrefixLength:ReadPrefixLength+UuidLength])
	} else if strings.HasPrefix(query, WritePrefix) {
		// If write operation, call doWrite() with tunnel UUID, ignoring any
		// characters following the tunnel UUID.
		err = s.doWrite(response, request, query[WritePrefixLength:WritePrefixLength+UuidLength])
	} else {
		// Otherwise, invalid operation
		err = ErrClient.NewError("Invalid tunnel operation: " + query)
	}

	return
}

/**
 * Called whenever the JavaScript Guacamole client makes a read request.
 * This function should in general not be overridden, as it already
 * contains a proper implementation of the read operation.
 *
 * @param request
 *     The HttpServletRequest associated with the read request received.
 *
 * @param response
 *     The HttpServletResponse associated with the write request received.
 *     Any data to be sent to the client in response to the write request
 *     should be written to the response body of this HttpServletResponse.
 *
 * @param tunnelUUID
 *     The UUID of the tunnel to read from, as specified in the write
 *     request. This tunnel must have been created by a previous call to
 *     doConnect().
 *
 * @throws ErrOther
 *     If an error occurs while handling the read request.
 */
func (s *HttpTunnelServlet) doRead(response http.ResponseWriter, request *http.Request, tunnelUUID string) (err error) {

	// Get tunnel, ensure tunnel exists
	tunnel, err := s.getTunnel(tunnelUUID)
	if err != nil {
		return
	}

	// Ensure tunnel is open
	if !tunnel.IsOpen() {
		s.deregisterTunnel(tunnel)
		err = ErrResourceNotFound.NewError("Tunnel is closed.")
		return
	}

	reader := tunnel.AcquireReader()
	defer tunnel.ReleaseReader()

	e := s.doReadCore1(response, reader, tunnel)

	if e != nil {

		// Log typically frequent I/O error if desired
		logger.Debug("Error writing to servlet output stream", e)

		// Deregister and close
		s.deregisterTunnel(tunnel)
		e = tunnel.Close()
	}

	return
}

func (s *HttpTunnelServlet) doReadCore1(response http.ResponseWriter, reader Reader, tunnel Tunnel) (e error) {
	// Note that although we are sending text, Webkit browsers will
	// buffer 1024 bytes before starting a normal stream if we use
	// anything but application/octet-stream.
	response.Header().Set("Content-Type", "application/octet-stream")
	response.Header().Set("Cache-Control", "no-cache")

	// response.Close() -->
	if v, ok := response.(http.Flusher); ok {
		v.Flush()
	}

	// Get writer for response
	// Writer out = new BufferedWriter(new OutputStreamWriter(response.getOutputStream(), "UTF-8"));

	// Stream data to response, ensuring output stream is closed
	err := s.doReadCore2(response, reader, tunnel)

	if err == nil {
		// success
		return
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
		// Deregister and close
		e = err
	}
	return
}

func (s *HttpTunnelServlet) doReadCore2(response http.ResponseWriter, reader Reader, tunnel Tunnel) (err error) {
	var ok bool
	var message []byte
	// Deregister tunnel and throw error if we reach EOF without
	// having ever sent any data
	message, err = reader.Read()
	if err != nil {
		return
	}

	// For all messages, until another stream is ready (we send at least one message)
	for ; tunnel.IsOpen() && len(message) > 0 && err == nil; message, err = reader.Read() {

		// Get message output bytes
		_, e := response.Write(message)
		if e != nil {
			err = ErrOther.NewError(e.Error())
			return
		}

		// Flush if we expect to wait
		ok, err = reader.Available()
		if err != nil {
			return
		}

		if !ok {
			if v, ok := response.(http.Flusher); ok {
				v.Flush()
			}
		}

		// No more messages another stream can take over
		if tunnel.HasQueuedReaderThreads() {
			break
		}
	}

	// Close tunnel immediately upon EOF
	if err != nil {
		s.deregisterTunnel(tunnel)
		tunnel.Close()
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

/**
 * Called whenever the JavaScript Guacamole client makes a write request.
 * This function should in general not be overridden, as it already
 * contains a proper implementation of the write operation.
 *
 * @param request
 *     The HttpServletRequest associated with the write request received.
 *     Any data to be written will be specified within the body of this
 *     request.
 *
 * @param response
 *     The HttpServletResponse associated with the write request received.
 *
 * @param tunnelUUID
 *     The UUID of the tunnel to write to, as specified in the write
 *     request. This tunnel must have been created by a previous call to
 *     doConnect().
 *
 * @throws ErrOther
 *     If an error occurs while handling the write request.
 */
func (s *HttpTunnelServlet) doWrite(response http.ResponseWriter, request *http.Request, tunnelUUID string) error {
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
		tunnel.Close()
	}

	return err
}

// Destroy release
func (s *HttpTunnelServlet) Destroy() {
	s.tunnels.Shutdown()
}
