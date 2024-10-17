package isardvdi

import (
	"fmt"
	"net/http"
)

type Err struct {
	Err             string  `json:"error"`
	Msg             string  `json:"msg"`
	Description     *string `json:"description,omitempty"`
	DescriptionCode *string `json:"description_code,omitempty"`
	StatusCode      int     `json:"-"`
	Params          *map[string]interface{}
}

func (e Err) Error() string {
	msg := fmt.Sprintf("http status code: %d: %s: %s", e.StatusCode, e.Err, e.Msg)

	if e.DescriptionCode != nil {
		msg += fmt.Sprintf(": %s", *e.DescriptionCode)
	}

	if e.Description != nil {
		msg += fmt.Sprintf(": %s", *e.Description)
	}

	if e.Params != nil {
		msg += fmt.Sprintf(": %+v", *e.Params)
	}

	return msg
}

func (e Err) Is(target error) bool {
	t, ok := target.(Err)
	if !ok {
		return false
	}

	if e.StatusCode != 0 {
		if e.StatusCode != t.StatusCode {
			return false
		}
	}

	return e.Err == t.Err &&
		e.Msg == t.Msg
}

var (
	ErrBadRequest = Err{
		Err:        "bad_request",
		Msg:        "Bad request",
		StatusCode: http.StatusBadRequest,
	}
	ErrUnauthorized = Err{
		Err:        "unauthorized",
		Msg:        "Unauthorized",
		StatusCode: http.StatusUnauthorized,
	}
	ErrForbidden = Err{
		Err:        "forbidden",
		Msg:        "Forbidden",
		StatusCode: http.StatusForbidden,
	}
	ErrNotFound = Err{
		Err:        "not_found",
		Msg:        "Not found",
		StatusCode: http.StatusNotFound,
	}
	ErrConflict = Err{
		Err:        "conflict",
		Msg:        "Conflict",
		StatusCode: http.StatusConflict,
	}
	ErrInternalServer = Err{
		Err:        "internal_server",
		Msg:        "Internal server error",
		StatusCode: http.StatusInternalServerError,
	}
	ErrGatewayTimeout = Err{
		Err:        "gateway_timeout",
		Msg:        "Gateway timeout",
		StatusCode: http.StatusGatewayTimeout,
	}
	ErrPreconditionRequired = Err{
		Err:        "precondition_required",
		Msg:        "Precondition required",
		StatusCode: http.StatusPreconditionRequired,
	}
	ErrInsufficientStorage = Err{
		Err:        "insufficient_storage",
		Msg:        "Insufficient storage",
		StatusCode: http.StatusInsufficientStorage,
	}
	ErrMaintenance = Err{
		Err:        "maintenance",
		Msg:        "Maintenance",
		StatusCode: http.StatusServiceUnavailable,
	}
)
