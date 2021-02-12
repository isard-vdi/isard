package middleware

import (
	"net/http"

	"github.com/rs/cors"
)

func (m *Middleware) cors(next http.Handler) http.Handler {
	c := cors.New(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowCredentials: true,
	})

	return c.Handler(next)
}
