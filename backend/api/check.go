package api

import (
	"net/http"
	"net/url"

	"github.com/gorilla/mux"
)

const redirectKey = "redirect"

func (a *API) check(w http.ResponseWriter, r *http.Request) {
	redirect := r.URL.Query().Get(redirectKey)
	if redirect == "" {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(getUsr(r.Context()).ID()))
		return
	}

	u, err := url.Parse(redirect)
	if err != nil {
		http.Error(w, "invalid redirect url", http.StatusBadRequest)
		return
	}

	http.Redirect(w, r, u.String(), http.StatusFound)
}

func (a *API) checkDesktop(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	ip, ok := vars["ip"]
	if !ok {
		http.Error(w, "unknown desktop", http.StatusBadRequest)
		return
	}

	u := getUsr(r.Context())
	for _, desktop := range u.Desktops {
		if desktop.IP == ip {
			w.WriteHeader(http.StatusOK)
			return
		}
	}

	http.Error(w, "permission denied", http.StatusForbidden)
}
