package guac

type Status int

const (
	// Undefined Add to instead null
	Undefined Status = -1

	/*Success *
	 * The operation succeeded.
	 */
	Success Status = iota

	/*Unsupported *
	 * The requested operation is unsupported.
	 */
	Unsupported

	/*SERVER_ERROR *
	 * The operation could not be performed due to an internal failure.
	 */
	ServerError

	/*SERVER_BUSY *
	 * The operation could not be performed as the server is busy.
	 */
	ServerBusy

	/*UPSTREAM_TIMEOUT *
	 * The operation could not be performed because the upstream server is not
	 * responding.
	 */
	UpstreamTimeout

	/*UPSTREAM_ERROR *
	 * The operation was unsuccessful due to an error or otherwise unexpected
	 * condition of the upstream server.
	 */
	UpstreamError

	/*RESOURCE_NOT_FOUND *
	 * The operation could not be performed as the requested resource does not
	 * exist.
	 */
	ResourceNotFound

	/*RESOURCE_CONFLICT *
	 * The operation could not be performed as the requested resource is already
	 * in use.
	 */
	ResourceConflict

	/*RESOURCE_CLOSED *
	 * The operation could not be performed as the requested resource is now
	 * closed.
	 */
	ResourceClosed

	/*UPSTREAM_NOT_FOUND *
	 * The operation could not be performed because the upstream server does
	 * not appear to exist.
	 */
	UpstreamNotFound

	/*UPSTREAM_UNAVAILABLE *
	 * The operation could not be performed because the upstream server is not
	 * available to service the request.
	 */
	UpstreamUnavailable

	/*SESSION_CONFLICT *
	 * The session within the upstream server has ended because it conflicted
	 * with another session.
	 */
	SessionConflict

	/*SESSION_TIMEOUT *
	 * The session within the upstream server has ended because it appeared to
	 * be inactive.
	 */
	SessionTimeout

	/*SESSION_CLOSED *
	 * The session within the upstream server has been forcibly terminated.
	 */
	SessionClosed

	/*CLIENT_BAD_REQUEST *
	 * The operation could not be performed because bad parameters were given.
	 */
	ClientBadRequest

	/*CLIENT_UNAUTHORIZED *
	 * Permission was denied to perform the operation, as the user is not yet
	 * authorized (not yet logged in, for example). As HTTP 401 has implications
	 * for HTTP-specific authorization schemes, this Status continues to map to
	 * HTTP 403 ("Forbidden"). To do otherwise would risk unintended effects.
	 */
	ClientUnauthorized

	/*CLIENT_FORBIDDEN *
	 * Permission was denied to perform the operation, and this operation will
	 * not be granted even if the user is authorized.
	 */
	ClientForbidden

	/*CLIENT_TIMEOUT *
	 * The client took too long to respond.
	 */
	ClientTimeout

	/*CLIENT_OVERRUN *
	 * The client sent too much data.
	 */
	ClientOverrun

	/*CLIENT_BAD_TYPE *
	 * The client sent data of an unsupported or unexpected type.
	 */
	ClientBadType

	/*CLIENT_TOO_MANY *
	 * The operation failed because the current client is already using too
	 * many resources.
	 */
	ClientTooMany
)

type statusData struct {
	name string
	/**
	 * The most applicable HTTP error code.
	 */
	httpCode int

	/**
	 * The most applicable WebSocket error code.
	 */
	websocketCode int

	/**
	 * The Guacamole protocol Status code.
	 */
	guacCode int
}

func newStatusData(name string, httpCode, websocketCode, guacCode int) (ret statusData) {
	ret.name = name
	ret.httpCode = httpCode
	ret.websocketCode = websocketCode
	ret.guacCode = guacCode
	return
}

var guacamoleStatusMap = map[Status]statusData{
	Success:             newStatusData("Success", 200, 1000, 0x0000),
	Unsupported:         newStatusData("Unsupported", 501, 1011, 0x0100),
	ServerError:         newStatusData("SERVER_ERROR", 500, 1011, 0x0200),
	ServerBusy:          newStatusData("SERVER_BUSY", 503, 1008, 0x0201),
	UpstreamTimeout:     newStatusData("UPSTREAM_TIMEOUT", 504, 1011, 0x0202),
	UpstreamError:       newStatusData("UPSTREAM_ERROR", 502, 1011, 0x0203),
	ResourceNotFound:    newStatusData("RESOURCE_NOT_FOUND", 404, 1002, 0x0204),
	ResourceConflict:    newStatusData("RESOURCE_CONFLICT", 409, 1008, 0x0205),
	ResourceClosed:      newStatusData("RESOURCE_CLOSED", 404, 1002, 0x0206),
	UpstreamNotFound:    newStatusData("UPSTREAM_NOT_FOUND", 502, 1011, 0x0207),
	UpstreamUnavailable: newStatusData("UPSTREAM_UNAVAILABLE", 502, 1011, 0x0208),
	SessionConflict:     newStatusData("SESSION_CONFLICT", 409, 1008, 0x0209),
	SessionTimeout:      newStatusData("SESSION_TIMEOUT", 408, 1002, 0x020A),
	SessionClosed:       newStatusData("SESSION_CLOSED", 404, 1002, 0x020B),
	ClientBadRequest:    newStatusData("CLIENT_BAD_REQUEST", 400, 1002, 0x0300),
	ClientUnauthorized:  newStatusData("CLIENT_UNAUTHORIZED", 403, 1008, 0x0301),
	ClientForbidden:     newStatusData("CLIENT_FORBIDDEN", 403, 1008, 0x0303),
	ClientTimeout:       newStatusData("CLIENT_TIMEOUT", 408, 1002, 0x0308),
	ClientOverrun:       newStatusData("CLIENT_OVERRUN", 413, 1009, 0x030D),
	ClientBadType:       newStatusData("CLIENT_BAD_TYPE", 415, 1003, 0x030F),
	ClientTooMany:       newStatusData("CLIENT_TOO_MANY", 429, 1008, 0x031D),
}

func (statue Status) String() string {
	if v, ok := guacamoleStatusMap[statue]; ok {
		return v.name
	}
	return ""
}

/*GetHTTPStatusCode *
 * Returns the most applicable HTTP error code.
 *
 * @return The most applicable HTTP error code.
 */
func (statue Status) GetHTTPStatusCode() int {
	if v, ok := guacamoleStatusMap[statue]; ok {
		return v.httpCode
	}
	return -1
}

/*GetWebSocketCode *
 * Returns the most applicable HTTP error code.
 *
 * @return The most applicable HTTP error code.
 */
func (statue Status) GetWebSocketCode() int {
	if v, ok := guacamoleStatusMap[statue]; ok {
		return v.websocketCode
	}
	return -1
}

/*GetGuacamoleStatusCode *
 * Returns the corresponding Guacamole protocol Status code.
 *
 * @return The corresponding Guacamole protocol Status code.
 */
func (statue Status) GetGuacamoleStatusCode() int {
	if v, ok := guacamoleStatusMap[statue]; ok {
		return v.guacCode
	}
	return -1
}

/*FromGuacamoleStatusCode *
 * Returns the Status corresponding to the given Guacamole
 * protocol Status code. If no such Status is defined, null is
 * returned.
 *
 * @param code
 *     The Guacamole protocol Status code to translate into a
 *     Status.
 *
 * @return
 *     The Status corresponding to the given Guacamole protocol
 *     Status code, or null if no such Status is defined.
 */
func FromGuacamoleStatusCode(code int) (ret Status) {
	// Search for a Status having the given Status code
	for k, v := range guacamoleStatusMap {
		if v.guacCode == code {
			ret = k
			return
		}
	}
	// No such Status found
	ret = Undefined
	return

}
