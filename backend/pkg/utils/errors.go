package utils

import (
	"fmt"
)

// ErrHTTPCode is an error that gets returned when a call to an API is not the HTTP Code that the program was expecting
type ErrHTTPCode struct {
	Code int
}

func (h *ErrHTTPCode) Error() string {
	return fmt.Sprintf("http code: %d", h.Code)
}

// NewHTTPCodeErr creates a new HTTPCodeErr
func NewHTTPCodeErr(code int) error {
	return &ErrHTTPCode{code}
}
