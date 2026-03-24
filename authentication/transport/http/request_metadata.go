package http

import (
	"context"
	"net/http"
	"strings"

	"github.com/ogen-go/ogen/middleware"
)

type requestMetadataCtxKeyType string

const (
	requestMetadataRemoteAddrCtxKey requestMetadataCtxKeyType = "request_metadata_remote_addr"
	requestMetadataHostCtxKey       requestMetadataCtxKeyType = "request_metadata_host"
)

func RequestMetadataOAS(
	req middleware.Request,
	next func(req middleware.Request) (middleware.Response, error),
) (middleware.Response, error) {
	remoteAddr := extractRemoteAddr(req.Raw)

	req.Context = context.WithValue(req.Context, requestMetadataRemoteAddrCtxKey, remoteAddr)
	req.Context = context.WithValue(req.Context, requestMetadataHostCtxKey, req.Raw.Host)

	return next(req)
}

func requestMetadataHandler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		remoteAddr := extractRemoteAddr(r)

		r = r.WithContext(context.WithValue(r.Context(), requestMetadataRemoteAddrCtxKey, remoteAddr))
		r = r.WithContext(context.WithValue(r.Context(), requestMetadataHostCtxKey, r.Host))

		next.ServeHTTP(w, r)
	})

}

func extractRemoteAddr(r *http.Request) string {
	remoteAddr := r.RemoteAddr
	if addr := r.Header.Get("X-Forwarded-For"); addr != "" {
		parts := strings.Split(addr, ",")
		remoteAddr = strings.TrimSpace(parts[len(parts)-1])
	}

	return remoteAddr
}
