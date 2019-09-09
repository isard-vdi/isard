package guac

import (
	"fmt"
	logger "github.com/sirupsen/logrus"
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

	/**
	 * Called whenever the JavaScript Guacamole client makes a connection
	 * request via HTTP. It it up to the implementor of this function to define
	 * what conditions must be met for a tunnel to be configured and returned
	 * as a result of this connection request (whether some sort of credentials
	 * must be specified, for example).
	 *
	 * @param request
	 *     The HttpServletRequest associated with the connection request
	 *     received. Any parameters specified along with the connection request
	 *     can be read from this object.
	 *
	 * @return
	 *     A newly constructed Tunnel if successful, null otherwise.
	 *
	 * @throws ErrOther
	 *     If an error occurs while constructing the Tunnel, or if the
	 *     conditions required for connection are not met.
	 */
	doConnect DoConnectInterface
}

// NewHTTPTunnelServlet Construct function
func NewHTTPTunnelServlet(doConnect DoConnectInterface) *HttpTunnelServlet {
	return &HttpTunnelServlet{
		tunnels:   NewHttpTunnelMap(),
		doConnect: doConnect,
	}
}

/**
 * Registers the given tunnel such that future read/write requests to that
 * tunnel will be properly directed.
 *
 * @param tunnel
 *     The tunnel to register.
 */
func (opt *HttpTunnelServlet) registerTunnel(tunnel Tunnel) {
	opt.tunnels.Put(tunnel.GetUUID().String(), tunnel)
	logger.Debugf("Registered tunnel \"%v\".", tunnel.GetUUID())
}

/**
 * Deregisters the given tunnel such that future read/write requests to
 * that tunnel will be rejected.
 *
 * @param tunnel
 *     The tunnel to deregister.
 */
func (opt *HttpTunnelServlet) deregisterTunnel(tunnel Tunnel) {
	opt.tunnels.Remove(tunnel.GetUUID().String())
	logger.Debugf("Deregistered tunnel \"%v\".", tunnel.GetUUID())
}

/**
 * Returns the tunnel with the given UUID, if it has been registered with
 * registerTunnel() and not yet deregistered with deregisterTunnel().
 *
 * @param tunnelUUID
 *     The UUID of registered tunnel.
 *
 * @return
 *     The tunnel corresponding to the given UUID.
 *
 * @throws ErrOther
 *     If the requested tunnel does not exist because it has not yet been
 *     registered or it has been deregistered.
 */
func (opt *HttpTunnelServlet) getTunnel(tunnelUUID string) (ret Tunnel,
	err error) {

	// Pull tunnel from map
	ret, ok := opt.tunnels.Get(tunnelUUID)

	if !ok {
		err = ErrResourceNotFound.NewError("No such tunnel.")
	}
	return
}

//DoGet @Override
func (opt *HttpTunnelServlet) DoGet(request HTTPServletRequestInterface, response HTTPServletResponseInterface) error {
	return opt.HandleTunnelRequest(request, response)
}

//DoPost @Override
func (opt *HttpTunnelServlet) DoPost(request HTTPServletRequestInterface, response HTTPServletResponseInterface) error {
	return opt.HandleTunnelRequest(request, response)
}

/**
 * Sends an error on the given HTTP response using the information within
 * the given Status.
 *
 * @param response
 *     The HTTP response to use to send the error.
 *
 * @param guacStatus
 *     The Status to send
 *
 * @param message
 *     A human-readable message that can be presented to the user.
 *
 * @throws ServletException
 *     If an error prevents sending of the error code.
 */
func (opt *HttpTunnelServlet) sendError(response HTTPServletResponseInterface, guacStatus Status, message string) (err error) {

	committed, err := response.IsCommitted()
	if err != nil {
		// If unable to send error at all due to I/O problems,
		// rethrow as servlet exception
		return
	}

	// If response not committed, send error code and message
	if !committed {
		response.AddHeader("Guacamole-Status-Code", fmt.Sprintf("%v", guacStatus.GetGuacamoleStatusCode()))
		response.AddHeader("Guacamole-Error-Message", message)
		err = response.SendError(guacStatus.GetHTTPStatusCode())
	}
	return
}

/*HandleTunnelRequest put it into GET/POST handle *
 * Dispatches every HTTP GET and POST request to the appropriate handler
 * function based on the query string.
 *
 * @param request
 *     The HttpServletRequest associated with the GET or POST request
 *     received.
 *
 * @param response
 *     The HttpServletResponse associated with the GET or POST request
 *     received.
 *
 * @throws ServletException
 *     If an error occurs while servicing the request.
 */
func (opt *HttpTunnelServlet) HandleTunnelRequest(request HTTPServletRequestInterface, response HTTPServletResponseInterface) (e error) {
	err := opt.handleTunnelRequestCore(request, response)
	if err == nil {
		return
	}
	guacErr := err.(*ErrGuac)
	switch guacErr.Kind {
	case ErrClient:
		logger.Warn("HTTP tunnel request rejected: ", err.Error())
		e = opt.sendError(response, guacErr.Status, err.Error())
	default:
		logger.Error("HTTP tunnel request failed: ", err.Error())
		logger.Debug("Internal error in HTTP tunnel.", err)
		e = opt.sendError(response, guacErr.Status, "Internal server error.")
	}
	return
}

func (opt *HttpTunnelServlet) handleTunnelRequestCore(request HTTPServletRequestInterface, response HTTPServletResponseInterface) (err error) {
	query := request.GetQueryString()
	if len(query) == 0 {
		return ErrClient.NewError("No query string provided.")
	}
	// If connect operation, call doConnect() and return tunnel UUID
	// in response.
	if query == "connect" {

		tunnel, e := opt.doConnect(request)

		// Failed to connect
		if e != nil {
			err = ErrResourceNotFound.NewError("No tunnel created.", e.Error())
			return
		}

		// Register newly-created tunnel
		opt.registerTunnel(tunnel)

		// Ensure buggy browsers do not cache response
		response.SetHeader("Cache-Control", "no-cache")

		// Send UUID to client
		e = response.WriteString(tunnel.GetUUID().String())

		if e != nil {
			err = ErrServer.NewError(e.Error())
			return
		}

	} else if strings.HasPrefix(query, ReadPrefix) {
		// If read operation, call doRead() with tunnel UUID, ignoring any
		// characters following the tunnel UUID.
		err = opt.doRead(request, response, query[ReadPrefixLength:ReadPrefixLength+UuidLength])
	} else if strings.HasPrefix(query, WritePrefix) {
		// If write operation, call doWrite() with tunnel UUID, ignoring any
		// characters following the tunnel UUID.
		err = opt.doWrite(request, response, query[WritePrefixLength:WritePrefixLength+UuidLength])
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
func (opt *HttpTunnelServlet) doRead(request HTTPServletRequestInterface,
	response HTTPServletResponseInterface, tunnelUUID string) (err error) {

	// Get tunnel, ensure tunnel exists
	tunnel, err := opt.getTunnel(tunnelUUID)
	if err != nil {
		return
	}

	// Ensure tunnel is open
	if !tunnel.IsOpen() {
		opt.deregisterTunnel(tunnel)
		err = ErrResourceNotFound.NewError("Tunnel is closed.")
		return
	}

	reader := tunnel.AcquireReader()
	defer tunnel.ReleaseReader()

	e := opt.doReadCore1(response, reader, tunnel)

	if e != nil {

		// Log typically frequent I/O error if desired
		logger.Debug("Error writing to servlet output stream", e)

		// Deregister and close
		opt.deregisterTunnel(tunnel)
		e = tunnel.Close()
	}

	return
}

func (opt *HttpTunnelServlet) doReadCore1(response HTTPServletResponseInterface, reader Reader, tunnel Tunnel) (e error) {
	// Note that although we are sending text, Webkit browsers will
	// buffer 1024 bytes before starting a normal stream if we use
	// anything but application/octet-stream.
	response.SetContentType("application/octet-stream")
	response.SetHeader("Cache-Control", "no-cache")

	// response.Close() -->
	defer response.FlushBuffer()

	// Get writer for response
	// Writer out = new BufferedWriter(new OutputStreamWriter(response.getOutputStream(), "UTF-8"));

	// Stream data to response, ensuring output stream is closed
	err := opt.doReadCore2(response, reader, tunnel)

	if err == nil {
		// success
		return
	}

	switch err.(*ErrGuac).Kind {
	// Send end-of-stream marker and close tunnel if connection is closed
	case ErrConnectionClosed:
		// Deregister and close
		opt.deregisterTunnel(tunnel)
		tunnel.Close()

		// End-of-instructions marker
		response.WriteString("0.;")
		response.FlushBuffer()
	default:
		// Deregister and close
		e = err
	}
	return
}

func (opt *HttpTunnelServlet) doReadCore2(response HTTPServletResponseInterface,
	reader Reader, tunnel Tunnel) (err error) {
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
		e := response.Write(message)
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
			e = response.FlushBuffer()
			if e != nil {
				err = ErrOther.NewError(e.Error())
				return
			}
		}

		// No more messages another stream can take over
		if tunnel.HasQueuedReaderThreads() {
			break
		}
	}

	// Close tunnel immediately upon EOF
	if err != nil {
		opt.deregisterTunnel(tunnel)
		tunnel.Close()
	}

	// End-of-instructions marker
	response.WriteString("0.;")
	response.FlushBuffer()
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
func (opt *HttpTunnelServlet) doWrite(request HTTPServletRequestInterface,
	response HTTPServletResponseInterface, tunnelUUID string) (err error) {
	tunnel, err := opt.getTunnel(tunnelUUID)
	if err != nil {
		return
	}

	// We still need to set the content type to avoid the default of
	// text/html, as such a content type would cause some browsers to
	// attempt to parse the result, even though the JavaScript client
	// does not explicitly request such parsing.
	response.SetContentType("application/octet-stream")
	response.SetHeader("Cache-Control", "no-cache")
	response.SetContentLength(0)

	writer := tunnel.AcquireWriter()
	defer tunnel.ReleaseWriter()

	var e error
	length := 0
	buffer := make([]byte, 1024, 1024)
	for length, e = request.Read(buffer); tunnel.IsOpen() && length > 0; length, e = request.Read(buffer) {
		err = writer.Write(buffer, 0, length)
		if err != nil {
			break
		}
	}
	if e != nil {
		// EOF
		// No need to close Request stream
		return nil
	}

	if err != nil {
		opt.deregisterTunnel(tunnel)
		tunnel.Close()
	}

	return
}

// Destroy release
func (opt *HttpTunnelServlet) Destroy() {
	opt.tunnels.Shutdown()
}
