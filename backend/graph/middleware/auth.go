package middleware

import (
	"context"
	"errors"
	"net/http"

	"gitlab.com/isard/isardvdi/backend/auth"
	"gitlab.com/isard/isardvdi/backend/model"
)

const cookieName = "auth"

var usrCtxKey = &contextKey{"usr"}

func (m *Middleware) auth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c, err := r.Cookie(cookieName)
		if err != nil || c == nil {
			next.ServeHTTP(w, r)
			return
		}

		u, err := m.Auth.GetUser(r.Context(), c)
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

func AuthForContext(ctx context.Context) *model.User {
	return ctx.Value(usrCtxKey).(*model.User)
}
