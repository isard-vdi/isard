package mocks

// WebRequest is a mock for querying a remote API
type WebRequest interface {
	Get(url string) ([]byte, int, error)
}
