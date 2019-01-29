package mocks

import (
	"io"
)

// WebRequest is a mock for querying a remote API
type WebRequest interface {
	Get(url string) ([]byte, int, error)
	Post(url string, body io.Reader) ([]byte, int, error)
}
