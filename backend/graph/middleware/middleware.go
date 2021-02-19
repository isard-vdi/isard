package middleware

import (
	"net/http"

	"gitlab.com/isard/isardvdi/pkg/proto/auth"

	"github.com/go-pg/pg/v10"
)

type contextKey struct {
	name string
}

type Middleware struct {
	DB   *pg.DB
	Auth auth.AuthClient
}

func NewMiddleware(db *pg.DB, auth auth.AuthClient) *Middleware {
	return &Middleware{
		DB:   db,
		Auth: auth,
	}
}

func (m *Middleware) Serve(next http.Handler) http.Handler {
	middleware := []func(http.Handler) http.Handler{
		m.cors,
		m.http,
		m.auth,
	}

	for i := len(middleware) - 1; i >= 0; i-- {
		next = middleware[i](next)
	}

	return next
}
