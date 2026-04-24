package http

import (
	"context"
	"net/http/httptest"
	"testing"

	"github.com/ogen-go/ogen/middleware"
	"github.com/stretchr/testify/assert"
)

func TestRequestMetadata(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareRequest func() middleware.Request
		CheckRequest   func(req middleware.Request) (middleware.Response, error)
	}{
		"should extract the IP correctly": {
			PrepareRequest: func() middleware.Request {
				raw := httptest.NewRequest("GET", "/", nil)
				raw.Header.Add("X-Forwarded-For", "192.168.1.1")
				raw.RemoteAddr = "172.0.0.1"
				raw.Host = "example.com"

				return middleware.Request{
					Context:          context.Background(),
					OperationID:      "test",
					OperationName:    "test",
					OperationSummary: "test",
					Body:             nil,
					Params:           middleware.Parameters{},
					Raw:              raw,
				}
			},
			CheckRequest: func(req middleware.Request) (middleware.Response, error) {
				remoteAddr := req.Context.Value(requestMetadataRemoteAddrCtxKey).(string)
				host := req.Context.Value(requestMetadataHostCtxKey).(string)

				assert.Equal("192.168.1.1", remoteAddr)
				assert.Equal("example.com", host)

				return middleware.Response{}, nil
			},
		},
		"should fallback to the remote address if the X-Formwarded-For header is missing": {
			PrepareRequest: func() middleware.Request {
				raw := httptest.NewRequest("GET", "/", nil)
				raw.RemoteAddr = "172.0.0.1"
				raw.Host = "isard.example.org"

				return middleware.Request{
					Context:          context.Background(),
					OperationID:      "test",
					OperationName:    "test",
					OperationSummary: "test",
					Body:             nil,
					Params:           middleware.Parameters{},
					Raw:              raw,
				}
			},
			CheckRequest: func(req middleware.Request) (middleware.Response, error) {
				remoteAddr := req.Context.Value(requestMetadataRemoteAddrCtxKey).(string)
				host := req.Context.Value(requestMetadataHostCtxKey).(string)

				assert.Equal("172.0.0.1", remoteAddr)
				assert.Equal("isard.example.org", host)

				return middleware.Response{}, nil
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			RequestMetadataOAS(tc.PrepareRequest(), tc.CheckRequest)
		})
	}
}
