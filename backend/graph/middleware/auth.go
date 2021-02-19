package middleware

import (
	"context"
	"net/http"

	"gitlab.com/isard/isardvdi/pkg/model"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"
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

		rsp, err := m.Auth.GetUserID(r.Context(), &auth.GetUserIDRequest{
			Token: c.Value,
		})
		if err != nil {
			// TODO
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		u := &model.User{ID: int(rsp.Id)}
		if err := u.Load(r.Context(), m.DB); err != nil {
			// TODO
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
