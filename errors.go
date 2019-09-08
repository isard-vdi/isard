package guac

import (
	"fmt"
	"strings"
)

type ExceptionKind int

type ExceptionInterface interface {
	Error() string
	GetStatus() Status
	GetMessage() string
	Kind() ExceptionKind
}

type exceptionData struct {
	err    error
	status Status
	kind   ExceptionKind
}

func (opt *exceptionData) GetStatus() Status {
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
	ServerException
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

// Status convert ExceptionKind to Status
func (exception ExceptionKind) Status() (state Status) {
	switch exception {
	case GuacamoleClientBadTypeException:
		return ClientBadType
	case GuacamoleClientException:
		return ClientBadRequest
	case GuacamoleClientOverrunException:
		return ClientOverrun
	case GuacamoleClientTimeoutException:
		return ClientTimeout
	case GuacamoleClientTooManyException:
		return ClientTooMany
	case GuacamoleConnectionClosedException:
		return ServerError
	case GuacamoleException:
		return ServerError
	case GuacamoleResourceClosedException:
		return ResourceClosed
	case GuacamoleResourceConflictException:
		return ResourceConflict
	case GuacamoleResourceNotFoundException:
		return ResourceNotFound
	case GuacamoleSecurityException:
		return ClientForbidden
	case GuacamoleServerBusyException:
		return ServerBusy
	case ServerException:
		return ServerError
	case GuacamoleSessionClosedException:
		return SessionClosed
	case GuacamoleSessionConflictException:
		return SessionConflict
	case GuacamoleSessionTimeoutException:
		return SessionTimeout
	case GuacamoleUnauthorizedException:
		return ClientUnauthorized
	case GuacamoleUnsupportedException:
		return Unsupported
	case GuacamoleUpstreamException:
		return UpstreamError
	case GuacamoleUpstreamNotFoundException:
		return UpstreamNotFound
	case GuacamoleUpstreamTimeoutException:
		return UpstreamTimeout
	case GuacamoleUpstreamUnavailableException:
		return UpstreamUnavailable
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
