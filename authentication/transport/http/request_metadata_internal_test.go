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
				// Remote address is injected in the RequestMetadata middleware
				remoteAddr := req.Context.Value(requestMetadataRemoteAddrCtxKey).(string)

				assert.Equal("192.168.1.1", remoteAddr)

				return middleware.Response{}, nil
			},
		},
		"should fallback to the remote address if the X-Formwarded-For header is missing": {
			PrepareRequest: func() middleware.Request {
				raw := httptest.NewRequest("GET", "/", nil)
				raw.RemoteAddr = "172.0.0.1"

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
				// Remote address is injected in the RequestMetadata middleware
				remoteAddr := req.Context.Value(requestMetadataRemoteAddrCtxKey).(string)

				assert.Equal("172.0.0.1", remoteAddr)

				return middleware.Response{}, nil
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			RequestMetadata(tc.PrepareRequest(), tc.CheckRequest)
		})
	}
}
