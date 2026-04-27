package ogenclient

import (
	"crypto/tls"
	"net/http"
)

// Option configures the HTTP client built by NewHTTPClient.
type Option func(*config)

type config struct {
	ignoreCerts bool
}

// WithIgnoreCerts disables TLS certificate verification.
func WithIgnoreCerts() Option {
	return func(c *config) { c.ignoreCerts = true }
}

// NewHTTPClient returns an *http.Client wired according to opts. The result is
// passed to ogen-generated client constructors (e.g.
// apiv4.NewClient(url, sec, apiv4.WithClient(httpClient))).
func NewHTTPClient(opts ...Option) *http.Client {
	cfg := &config{}
	for _, opt := range opts {
		opt(cfg)
	}

	if !cfg.ignoreCerts {
		return http.DefaultClient
	}

	transport, ok := http.DefaultTransport.(*http.Transport)
	if !ok {
		transport = &http.Transport{}
	}
	t := transport.Clone()
	t.TLSClientConfig = &tls.Config{InsecureSkipVerify: true} //nolint:gosec // explicit opt-in.

	return &http.Client{Transport: t}
}
