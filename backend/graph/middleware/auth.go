package middleware

import (
	"context"
	"errors"
	"net/http"

	"gitlab.com/isard/isardvdi/backend/auth"
	"gitlab.com/isard/isardvdi/backend/model"
)

type contextKey struct {
	name string
}

var usrCtxKey = &contextKey{"usr"}

func AuthMiddleware(a *auth.Auth) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			c, err := r.Cookie("auth-cookie")
			if err != nil || c == nil {
				// TODO: What do we do?
				http.Error(w, err.Error(), http.StatusUnauthorized)
				return
			}

			u, err := a.GetUser(r.Context(), c)
			if err != nil {
				if errors.Is(err, auth.ErrNotAuthenticated) {
					http.Error(w, err.Error(), http.StatusUnauthorized)
					return
				}

				// TODO: Should this error be sent to the user?
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}

			r = r.WithContext(context.WithValue(r.Context(), usrCtxKey, u))
			next.ServeHTTP(w, r)
		})
	}
}

func ForContext(ctx context.Context) *model.User {
	return ctx.Value(usrCtxKey).(*model.User)
}
