package guac

// HTTPServletRequestInterface convert http request
type HTTPServletRequestInterface interface {
	// Returns the query string that is contained in the request URL after the path. This method returns null if the URL does not have a query string. Same as the value of the CGI variable QUERY_STRING.
	GetQueryString() string
	Read([]byte) (int, error)
}

// HTTPServletResponseInterface convert http response
type HTTPServletResponseInterface interface {
	// Returns a boolean indicating if the response has been committed. A committed response has already had its status code and headers written.
	IsCommitted() (bool, error)

	// Adds a response header with the given name and value. This method allows response headers to have multiple values.
	AddHeader(key, value string)

	// Sets a response header with the given name and value. If the header had already been set, the new value overwrites the previous one. The containsHeader method can be used to test for the presence of a header before setting its value.
	SetHeader(key, value string)

	// Sets the content type of the response being sent to the client
	SetContentType(value string)

	SetContentLength(length int)

	// Sends an error response to the client using the specified status code and clearing the buffer.
	SendError(sc int) error

	// Instread of getWriter().print
	WriteString(data string) error

	// Instread of getWriter().print
	Write(data []byte) error

	FlushBuffer() error
	Close() error
}

// DoConnectInterface Tool interface for HttpTunnelServlet
type DoConnectInterface func(request HTTPServletRequestInterface) (Tunnel, error)

// GetSocketInterface Tool interface for BaseTunnel
type GetSocketInterface interface {
	GetSocket() Socket
}
