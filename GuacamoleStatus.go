package guac

type GuacamoleStatus int

const (
	// Undifined Add to instead null
	Undifined GuacamoleStatus = -1

	/*SUCCESS *
	 * The operation succeeded.
	 */
	SUCCESS GuacamoleStatus = iota

	/*UNSUPPORTED *
	 * The requested operation is unsupported.
	 */
	UNSUPPORTED

	/*SERVER_ERROR *
	 * The operation could not be performed due to an internal failure.
	 */
	SERVER_ERROR

	/*SERVER_BUSY *
	 * The operation could not be performed as the server is busy.
	 */
	SERVER_BUSY

	/*UPSTREAM_TIMEOUT *
	 * The operation could not be performed because the upstream server is not
	 * responding.
	 */
	UPSTREAM_TIMEOUT

	/*UPSTREAM_ERROR *
	 * The operation was unsuccessful due to an error or otherwise unexpected
	 * condition of the upstream server.
	 */
	UPSTREAM_ERROR

	/*RESOURCE_NOT_FOUND *
	 * The operation could not be performed as the requested resource does not
	 * exist.
	 */
	RESOURCE_NOT_FOUND

	/*RESOURCE_CONFLICT *
	 * The operation could not be performed as the requested resource is already
	 * in use.
	 */
	RESOURCE_CONFLICT

	/*RESOURCE_CLOSED *
	 * The operation could not be performed as the requested resource is now
	 * closed.
	 */
	RESOURCE_CLOSED

	/*UPSTREAM_NOT_FOUND *
	 * The operation could not be performed because the upstream server does
	 * not appear to exist.
	 */
	UPSTREAM_NOT_FOUND

	/*UPSTREAM_UNAVAILABLE *
	 * The operation could not be performed because the upstream server is not
	 * available to service the request.
	 */
	UPSTREAM_UNAVAILABLE

	/*SESSION_CONFLICT *
	 * The session within the upstream server has ended because it conflicted
	 * with another session.
	 */
	SESSION_CONFLICT

	/*SESSION_TIMEOUT *
	 * The session within the upstream server has ended because it appeared to
	 * be inactive.
	 */
	SESSION_TIMEOUT

	/*SESSION_CLOSED *
	 * The session within the upstream server has been forcibly terminated.
	 */
	SESSION_CLOSED

	/*CLIENT_BAD_REQUEST *
	 * The operation could not be performed because bad parameters were given.
	 */
	CLIENT_BAD_REQUEST

	/*CLIENT_UNAUTHORIZED *
	 * Permission was denied to perform the operation, as the user is not yet
	 * authorized (not yet logged in, for example). As HTTP 401 has implications
	 * for HTTP-specific authorization schemes, this status continues to map to
	 * HTTP 403 ("Forbidden"). To do otherwise would risk unintended effects.
	 */
	CLIENT_UNAUTHORIZED

	/*CLIENT_FORBIDDEN *
	 * Permission was denied to perform the operation, and this operation will
	 * not be granted even if the user is authorized.
	 */
	CLIENT_FORBIDDEN

	/*CLIENT_TIMEOUT *
	 * The client took too long to respond.
	 */
	CLIENT_TIMEOUT

	/*CLIENT_OVERRUN *
	 * The client sent too much data.
	 */
	CLIENT_OVERRUN

	/*CLIENT_BAD_TYPE *
	 * The client sent data of an unsupported or unexpected type.
	 */
	CLIENT_BAD_TYPE

	/*CLIENT_TOO_MANY *
	 * The operation failed because the current client is already using too
	 * many resources.
	 */
	CLIENT_TOO_MANY
)

type guacamoleStatusData struct {
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
	 * The Guacamole protocol status code.
	 */
	guacCode int
}

func newGuacamoleStatusData(name string, httpCode, websocketCode, guacCode int) (ret guacamoleStatusData) {
	ret.name = name
	ret.httpCode = httpCode
	ret.websocketCode = websocketCode
	ret.guacCode = guacCode
	return
}

var guacamoleStatusMap = initGuacamoleStatusMap()

func initGuacamoleStatusMap() (ret map[GuacamoleStatus]guacamoleStatusData) {
	ret = make(map[GuacamoleStatus]guacamoleStatusData)
	/**
	 * The operation succeeded.
	 */
	ret[SUCCESS] = newGuacamoleStatusData("SUCCESS", 200, 1000, 0x0000)

	/**
	 * The requested operation is unsupported.
	 */
	ret[UNSUPPORTED] = newGuacamoleStatusData("UNSUPPORTED", 501, 1011, 0x0100)

	/**
	 * The operation could not be performed due to an internal failure.
	 */
	ret[SERVER_ERROR] = newGuacamoleStatusData("SERVER_ERROR", 500, 1011, 0x0200)

	/**
	 * The operation could not be performed as the server is busy.
	 */
	ret[SERVER_BUSY] = newGuacamoleStatusData("SERVER_BUSY", 503, 1008, 0x0201)

	/**
	 * The operation could not be performed because the upstream server is not
	 * responding.
	 */
	ret[UPSTREAM_TIMEOUT] = newGuacamoleStatusData("UPSTREAM_TIMEOUT", 504, 1011, 0x0202)

	/**
	 * The operation was unsuccessful due to an error or otherwise unexpected
	 * condition of the upstream server.
	 */
	ret[UPSTREAM_ERROR] = newGuacamoleStatusData("UPSTREAM_ERROR", 502, 1011, 0x0203)

	/**
	 * The operation could not be performed as the requested resource does not
	 * exist.
	 */
	ret[RESOURCE_NOT_FOUND] = newGuacamoleStatusData("RESOURCE_NOT_FOUND", 404, 1002, 0x0204)

	/**
	 * The operation could not be performed as the requested resource is already
	 * in use.
	 */
	ret[RESOURCE_CONFLICT] = newGuacamoleStatusData("RESOURCE_CONFLICT", 409, 1008, 0x0205)

	/**
	 * The operation could not be performed as the requested resource is now
	 * closed.
	 */
	ret[RESOURCE_CLOSED] = newGuacamoleStatusData("RESOURCE_CLOSED", 404, 1002, 0x0206)

	/**
	 * The operation could not be performed because the upstream server does
	 * not appear to exist.
	 */
	ret[UPSTREAM_NOT_FOUND] = newGuacamoleStatusData("UPSTREAM_NOT_FOUND", 502, 1011, 0x0207)

	/**
	 * The operation could not be performed because the upstream server is not
	 * available to service the request.
	 */
	ret[UPSTREAM_UNAVAILABLE] = newGuacamoleStatusData("UPSTREAM_UNAVAILABLE", 502, 1011, 0x0208)

	/**
	 * The session within the upstream server has ended because it conflicted
	 * with another session.
	 */
	ret[SESSION_CONFLICT] = newGuacamoleStatusData("SESSION_CONFLICT", 409, 1008, 0x0209)

	/**
	 * The session within the upstream server has ended because it appeared to
	 * be inactive.
	 */
	ret[SESSION_TIMEOUT] = newGuacamoleStatusData("SESSION_TIMEOUT", 408, 1002, 0x020A)

	/**
	 * The session within the upstream server has been forcibly terminated.
	 */
	ret[SESSION_CLOSED] = newGuacamoleStatusData("SESSION_CLOSED", 404, 1002, 0x020B)

	/**
	 * The operation could not be performed because bad parameters were given.
	 */
	ret[CLIENT_BAD_REQUEST] = newGuacamoleStatusData("CLIENT_BAD_REQUEST", 400, 1002, 0x0300)

	/**
	 * Permission was denied to perform the operation, as the user is not yet
	 * authorized (not yet logged in, for example). As HTTP 401 has implications
	 * for HTTP-specific authorization schemes, this status continues to map to
	 * HTTP 403 ("Forbidden"). To do otherwise would risk unintended effects.
	 */
	ret[CLIENT_UNAUTHORIZED] = newGuacamoleStatusData("CLIENT_UNAUTHORIZED", 403, 1008, 0x0301)

	/**
	 * Permission was denied to perform the operation, and this operation will
	 * not be granted even if the user is authorized.
	 */
	ret[CLIENT_FORBIDDEN] = newGuacamoleStatusData("CLIENT_FORBIDDEN", 403, 1008, 0x0303)

	/**
	 * The client took too long to respond.
	 */
	ret[CLIENT_TIMEOUT] = newGuacamoleStatusData("CLIENT_TIMEOUT", 408, 1002, 0x0308)

	/**
	 * The client sent too much data.
	 */
	ret[CLIENT_OVERRUN] = newGuacamoleStatusData("CLIENT_OVERRUN", 413, 1009, 0x030D)

	/**
	 * The client sent data of an unsupported or unexpected type.
	 */
	ret[CLIENT_BAD_TYPE] = newGuacamoleStatusData("CLIENT_BAD_TYPE", 415, 1003, 0x030F)

	/**
	 * The operation failed because the current client is already using too
	 * many resources.
	 */
	ret[CLIENT_TOO_MANY] = newGuacamoleStatusData("CLIENT_TOO_MANY", 429, 1008, 0x031D)
	return
}

func (statue GuacamoleStatus) String() string {
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
func (statue GuacamoleStatus) GetHTTPStatusCode() int {
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
func (statue GuacamoleStatus) GetWebSocketCode() int {
	if v, ok := guacamoleStatusMap[statue]; ok {
		return v.websocketCode
	}
	return -1
}

/*GetGuacamoleStatusCode *
 * Returns the corresponding Guacamole protocol status code.
 *
 * @return The corresponding Guacamole protocol status code.
 */
func (statue GuacamoleStatus) GetGuacamoleStatusCode() int {
	if v, ok := guacamoleStatusMap[statue]; ok {
		return v.guacCode
	}
	return -1
}

/*FromGuacamoleStatusCode *
 * Returns the GuacamoleStatus corresponding to the given Guacamole
 * protocol status code. If no such GuacamoleStatus is defined, null is
 * returned.
 *
 * @param code
 *     The Guacamole protocol status code to translate into a
 *     GuacamoleStatus.
 *
 * @return
 *     The GuacamoleStatus corresponding to the given Guacamole protocol
 *     status code, or null if no such GuacamoleStatus is defined.
 */
func FromGuacamoleStatusCode(code int) (ret GuacamoleStatus) {
	// Search for a GuacamoleStatus having the given status code
	for k, v := range guacamoleStatusMap {
		if v.guacCode == code {
			ret = k
			return
		}
	}
	// No such status found
	ret = Undifined
	return

}
