package http

import (
	"context"
	"strings"

	"github.com/ogen-go/ogen/middleware"
)

type requestMetadataCtxKeyType string

const requestMetadataRemoteAddrCtxKey requestMetadataCtxKeyType = "request_metadata_remote_addr"

func RequestMetadata(
	req middleware.Request,
	next func(req middleware.Request) (middleware.Response, error),
) (middleware.Response, error) {
	remoteAddr := req.Raw.RemoteAddr
	if addr := req.Raw.Header.Get("X-Forwarded-For"); addr != "" {
		remoteAddr = strings.TrimSpace(strings.Split(addr, ",")[0])
	}

	req.Context = context.WithValue(req.Context, requestMetadataRemoteAddrCtxKey, remoteAddr)

	return next(req)
}
