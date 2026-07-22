package ogenclient_test

import (
	"net/http"
	"testing"

	"gitlab.com/isard/isardvdi/pkg/ogenclient"
)

func TestNewHTTPClient_Default(t *testing.T) {
	t.Parallel()
	c := ogenclient.NewHTTPClient()
	if c == nil {
		t.Fatal("expected non-nil client")
	}
}

func TestNewHTTPClient_IgnoreCerts(t *testing.T) {
	t.Parallel()
	c := ogenclient.NewHTTPClient(ogenclient.WithIgnoreCerts())
	tr, ok := c.Transport.(*http.Transport)
	if !ok || tr.TLSClientConfig == nil || !tr.TLSClientConfig.InsecureSkipVerify {
		t.Fatal("expected insecure-skip transport")
	}
}
