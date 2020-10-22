package middleware

import (
	"net/http"

	"gitlab.com/isard/isardvdi/backend/auth"
)

type contextKey struct {
	name string
}

type Middleware struct {
	Auth *auth.Auth
}

func NewMiddleware(auth *auth.Auth) *Middleware {
	return &Middleware{
		Auth: auth,
	}
}

func (m *Middleware) Serve(next http.Handler) http.Handler {
	middleware := []func(http.Handler) http.Handler{
		m.http,
		m.auth,
	}

	for i := len(middleware) - 1; i >= 0; i-- {
		next = middleware[i](next)
	}

	return next
}
