package middleware

import (
	"context"
	"errors"
	"net/http"

	"gitlab.com/isard/isardvdi/pkg/model"
	"gitlab.com/isard/isardvdi/pkg/proto/auth"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// headerName is the name of the HTTP header where the token is going to be search
const headerName = "Authorization"

var (
	usrCtxKey      = &contextKey{"usr"}
	entityIDCtxKey = &contextKey{"entityID"}
	// ErrNotAuthenticated is returned when the user tries to access an endpoint and is not authenticated or has an invalid token
	ErrNotAuthenticated = errors.New("not authenticated")
)

// auth handles the authentication
// TODO: Authorization
func (m *Middleware) auth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := r.Header.Get(headerName)
		if h == "" {
			next.ServeHTTP(w, r)
			return
		}

		rsp, err := m.Auth.GetUserID(r.Context(), &auth.GetUserIDRequest{
			Token: h,
		})
		if err != nil {
			if status.Code(err) == codes.Unauthenticated {
				next.ServeHTTP(w, r)
				return
			}

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

		r = r.WithContext(SetAuthContext(r.Context(), u, int(rsp.EntityId)))
		next.ServeHTTP(w, r)
	})
}

// SetAuthContext sets the authentication info to the context
func SetAuthContext(ctx context.Context, u *model.User, eID int) context.Context {
	ctx = context.WithValue(ctx, usrCtxKey, u)
	return context.WithValue(ctx, entityIDCtxKey, eID)
}

// AuthForContext returns the authentication info of a context
func AuthForContext(ctx context.Context) (*model.User, int) {
	usr, _ := ctx.Value(usrCtxKey).(*model.User)
	entityID, _ := ctx.Value(entityIDCtxKey).(int)

	return usr, entityID
}

// IsAuthenticated checks if the context has authentication info
func IsAuthenticated(ctx context.Context) error {
	u, _ := AuthForContext(ctx)
	if u == nil {
		return ErrNotAuthenticated
	}

	return nil
}
