package api

import (
	"net/http"
	"net/url"
)

const redirectKey = "redirect"

func (a *API) check(w http.ResponseWriter, r *http.Request) {
	redirect := r.URL.Query().Get(redirectKey)
	if redirect == "" {
		w.WriteHeader(http.StatusOK)
		return
	}

	u, err := url.Parse(redirect)
	if err != nil {
		http.Error(w, "invalid redirect url", http.StatusBadRequest)
		return
	}

	http.Redirect(w, r, u.String(), http.StatusFound)
}
