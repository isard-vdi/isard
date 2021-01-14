package middleware

import (
	"github.com/rs/cors"
	"net/http"
)

func (m *Middleware) cors(next http.Handler) http.Handler {
	c := cors.New(cors.Options{
		AllowedOrigins: []string{"*"},
		AllowCredentials: true,
	})

	return c.Handler(next)
}