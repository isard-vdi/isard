package api

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"

	"github.com/go-redis/redis"
	"github.com/gorilla/mux"
	"github.com/isard-vdi/isard/backend/auth"
	"github.com/isard-vdi/isard/backend/auth/provider"
	"github.com/isard-vdi/isard/backend/env"
	"github.com/isard-vdi/isard/backend/model"
	"github.com/isard-vdi/isard/backend/pkg/utils"
)

type contextKey int

const (
	version                         = "v2"
	mainteinanceRedisKey            = "manteinance"
	usrCtxKey            contextKey = 0
)

var (
	manteinanceAdmins []string
)

func init() {
	manteinanceAdmins = strings.Split(os.Getenv("BACKEND_MANTEINANCE_ADMINS"), ",")
}

// API is the main API handler
type API struct {
	env *env.Env
	Mux *mux.Router
}

// New creates the API handler
func New(env *env.Env) *API {
	a := &API{
		env,
		mux.NewRouter(),
	}

	a.Mux.HandleFunc("/api/"+version+"/config", a.configuration)
	a.Mux.HandleFunc("/api/"+version+"/categories", a.categories)
	a.Mux.HandleFunc("/api/"+version+"/category/{category}", a.category)

	a.Mux.HandleFunc("/api/"+version+"/login/", a.login)
	a.Mux.HandleFunc("/api/"+version+"/login/{category}", a.login)
	a.Mux.HandleFunc("/api/"+version+"/register", a.register)

	a.Mux.HandleFunc("/callback/{provider}", func(w http.ResponseWriter, r *http.Request) {
		provider.Callback(env, w, r)
	})
	a.Mux.HandleFunc("/api/"+version+"/logout", a.isAuthenticated(a.logout))

	a.Mux.HandleFunc("/api/"+version+"/check", a.isAuthenticated(a.check))
	a.Mux.HandleFunc("/api/"+version+"/templates", a.isAuthenticated(a.templates))
	a.Mux.HandleFunc("/api/"+version+"/create", a.isAuthenticated(a.create))

	a.Mux.HandleFunc("/api/"+version+"/desktops", a.isAuthenticated(a.desktops))
	a.Mux.HandleFunc("/api/"+version+"/desktop/{desktop}", a.isAuthenticated(a.desktopDelete)).Methods("DELETE")
	a.Mux.HandleFunc("/api/"+version+"/desktop/{desktop}/start", a.isAuthenticated(a.desktopStart))
	a.Mux.HandleFunc("/api/"+version+"/desktop/{desktop}/stop", a.isAuthenticated(a.desktopStop))
	a.Mux.HandleFunc("/api/"+version+"/desktop/{desktop}/viewer/{viewerType}", a.isAuthenticated(a.desktopViewer))

	return a
}

func (a *API) isAuthenticated(handler http.HandlerFunc) http.HandlerFunc {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		manteinance, err := a.env.Redis.WithContext(r.Context()).Do("GET", mainteinanceRedisKey).Bool()
		if err != nil {
			if !errors.Is(err, redis.Nil) {
				a.env.Sugar.Errorw("get manteinance status",
					"err", err,
				)

				w.WriteHeader(http.StatusInternalServerError)
				return
			}
		}

		if manteinance {
			http.Error(w, "service in mainteinance", http.StatusServiceUnavailable)
			return
		}

		c, err := r.Cookie(provider.SessionStoreKey)
		if err != nil || c == nil {
			http.Error(w, "Unauthenticated", http.StatusUnauthorized)
			return
		}

		u, err := auth.IsAuthenticated(r.Context(), a.env, c)
		if err != nil {
			http.Error(w, err.Error(), http.StatusUnauthorized)
			return
		}

		r = r.WithContext(context.WithValue(r.Context(), usrCtxKey, u))

		isardCookie, err := getCookie(r)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		if err := isardCookie.update(u, w); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		handler.ServeHTTP(w, r)
	})
}

func getUsr(ctx context.Context) *model.User {
	usr, _ := ctx.Value(usrCtxKey).(*model.User)
	return usr
}

func handleErr(err error, w http.ResponseWriter, r *http.Request) {
	var e *utils.ErrHTTPCode
	if errors.As(err, &e) {
		w.WriteHeader(e.Code)
	} else {
		w.WriteHeader(http.StatusInternalServerError)
	}

	fmt.Fprint(w, err)
}

func handleErrRedirect(err error, w http.ResponseWriter, r *http.Request) {
	var e *utils.ErrHTTPCode
	if errors.As(err, &e) {
		http.Redirect(w, r, "/error/"+strconv.Itoa(e.Code), http.StatusFound)
		return
	}

	http.Redirect(w, r, "/error/500", http.StatusFound)
}
