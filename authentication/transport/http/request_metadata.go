package http

import (
	"context"
	"net/http"
	"strings"

	"github.com/ogen-go/ogen/middleware"
)

type requestMetadataCtxKeyType string

const requestMetadataRemoteAddrCtxKey requestMetadataCtxKeyType = "request_metadata_remote_addr"

func RequestMetadataOAS(
	req middleware.Request,
	next func(req middleware.Request) (middleware.Response, error),
) (middleware.Response, error) {
	remoteAddr := extractRemoteAddr(req.Raw)

	req.Context = context.WithValue(req.Context, requestMetadataRemoteAddrCtxKey, remoteAddr)

	return next(req)
}

func requestMetadataHandler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		remoteAddr := extractRemoteAddr(r)

		r = r.WithContext(context.WithValue(r.Context(), requestMetadataRemoteAddrCtxKey, remoteAddr))

		next.ServeHTTP(w, r)
	})

}

func extractRemoteAddr(r *http.Request) string {
	remoteAddr := r.RemoteAddr
	if addr := r.Header.Get("X-Forwarded-For"); addr != "" {
		remoteAddr = strings.TrimSpace(strings.Split(addr, ",")[0])
	}

	return remoteAddr
}
