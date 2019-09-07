package guac

import (
	"fmt"
	"strings"
)

type ExceptionKind int

type ExceptionInterface interface {
	Error() string
	GetStatus() GuacamoleStatus
	GetMessage() string
	Kind() ExceptionKind
}

type exceptionData struct {
	err    error
	status GuacamoleStatus
	kind   ExceptionKind
}

func (opt *exceptionData) GetStatus() GuacamoleStatus {
	return opt.status
}

func (opt *exceptionData) GetMessage() string {
	return opt.err.Error()
}

func (opt *exceptionData) Error() string {
	return opt.err.Error()
}

func (opt *exceptionData) Kind() ExceptionKind {
	return opt.kind
}

// Value of ExceptionKind
const (
	GuacamoleClientBadTypeException ExceptionKind = iota
	GuacamoleClientException
	GuacamoleClientOverrunException
	GuacamoleClientTimeoutException
	GuacamoleClientTooManyException
	GuacamoleConnectionClosedException
	GuacamoleException
	GuacamoleResourceClosedException
	GuacamoleResourceConflictException
	GuacamoleResourceNotFoundException
	GuacamoleSecurityException
	GuacamoleServerBusyException
	GuacamoleServerException
	GuacamoleSessionClosedException
	GuacamoleSessionConflictException
	GuacamoleSessionTimeoutException
	GuacamoleUnauthorizedException
	GuacamoleUnsupportedException
	GuacamoleUpstreamException
	GuacamoleUpstreamNotFoundException
	GuacamoleUpstreamTimeoutException
	GuacamoleUpstreamUnavailableException
)

// Status convert ExceptionKind to GuacamoleStatus
func (exception ExceptionKind) Status() (state GuacamoleStatus) {
	switch exception {
	case GuacamoleClientBadTypeException:
		return CLIENT_BAD_TYPE
	case GuacamoleClientException:
		return CLIENT_BAD_REQUEST
	case GuacamoleClientOverrunException:
		return CLIENT_OVERRUN
	case GuacamoleClientTimeoutException:
		return CLIENT_TIMEOUT
	case GuacamoleClientTooManyException:
		return CLIENT_TOO_MANY
	case GuacamoleConnectionClosedException:
		return SERVER_ERROR
	case GuacamoleException:
		return SERVER_ERROR
	case GuacamoleResourceClosedException:
		return RESOURCE_CLOSED
	case GuacamoleResourceConflictException:
		return RESOURCE_CONFLICT
	case GuacamoleResourceNotFoundException:
		return RESOURCE_NOT_FOUND
	case GuacamoleSecurityException:
		return CLIENT_FORBIDDEN
	case GuacamoleServerBusyException:
		return SERVER_BUSY
	case GuacamoleServerException:
		return SERVER_ERROR
	case GuacamoleSessionClosedException:
		return SESSION_CLOSED
	case GuacamoleSessionConflictException:
		return SESSION_CONFLICT
	case GuacamoleSessionTimeoutException:
		return SESSION_TIMEOUT
	case GuacamoleUnauthorizedException:
		return CLIENT_UNAUTHORIZED
	case GuacamoleUnsupportedException:
		return UNSUPPORTED
	case GuacamoleUpstreamException:
		return UPSTREAM_ERROR
	case GuacamoleUpstreamNotFoundException:
		return UPSTREAM_NOT_FOUND
	case GuacamoleUpstreamTimeoutException:
		return UPSTREAM_TIMEOUT
	case GuacamoleUpstreamUnavailableException:
		return UPSTREAM_UNAVAILABLE
	}
	return
}

// Throw Build one ExceptionInterface by ExceptionKind
func (exception ExceptionKind) Throw(args ...string) (err ExceptionInterface) {
	err = &exceptionData{
		err:    fmt.Errorf("%v", strings.Join(args, ", ")),
		status: exception.Status(),
		kind:   exception,
	}
	return
}
