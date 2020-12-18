package middleware

import (
	"context"
	"net/http"
)

var httpKey = &contextKey{"http"}

type requestHTTP struct {
	W *http.ResponseWriter
	R *http.Request
}

func (m *Middleware) http(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		r = r.WithContext(context.WithValue(r.Context(), httpKey, &requestHTTP{
			W: &w,
			R: r,
		}))

		next.ServeHTTP(w, r)
	})
}

func GetHTTP(ctx context.Context) *requestHTTP {
	return ctx.Value(httpKey).(*requestHTTP)
}
