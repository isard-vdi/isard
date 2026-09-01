package ogenclient

import (
	"crypto/tls"
	"net/http"
)

const maxIdleConnsPerHost = 100

// Option configures the HTTP client built by NewHTTPClient.
type Option func(*config)

type config struct {
	ignoreCerts bool
	userAgent   string
}

// WithIgnoreCerts disables TLS certificate verification.
func WithIgnoreCerts() Option {
	return func(c *config) {
		c.ignoreCerts = true
	}
}

// WithUserAgent identifies the caller in the API's request logs. Without
// it net/http sends "Go-http-client/1.1", which the request provenance
// helper in isardvdi_common cannot tell apart from any other Go service.
func WithUserAgent(userAgent string) Option {
	return func(c *config) {
		c.userAgent = userAgent
	}
}

type userAgentTransport struct {
	Transport http.RoundTripper
	userAgent string
}

func (u *userAgentTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	req.Header.Set("User-Agent", u.userAgent)

	return u.Transport.RoundTrip(req)
}

// NewHTTPClient returns an *http.Client wired according to opts, with its
// own transport and therefore its own connection pool: build it once and
// keep it. The result is passed to ogen-generated client constructors
// (e.g. apiv4.NewClient(url, sec, apiv4.WithClient(httpClient))).
func NewHTTPClient(opts ...Option) *http.Client {
	cfg := &config{}
	for _, opt := range opts {
		opt(cfg)
	}

	transport, ok := http.DefaultTransport.(*http.Transport)
	if !ok {
		transport = &http.Transport{}
	}

	t := transport.Clone()
	t.MaxIdleConnsPerHost = maxIdleConnsPerHost

	if cfg.ignoreCerts {
		t.TLSClientConfig = &tls.Config{InsecureSkipVerify: true} //nolint:gosec // explicit opt-in.
	}

	if cfg.userAgent == "" {
		return &http.Client{Transport: t}
	}

	return &http.Client{
		Transport: &userAgentTransport{
			Transport: t,
			userAgent: cfg.userAgent,
		},
	}
}
