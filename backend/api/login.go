package api

import (
	"net/http"

	"github.com/gorilla/mux"
	"github.com/isard-vdi/isard/backend/auth/provider"
)

func (a *API) login(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	category, _ := vars[provider.CategoryKey]

	p := provider.FromString(r.FormValue("provider"))
	if p.String() == "unknown" {
		http.Error(w, "unknown identity provider", http.StatusBadRequest)
		return
	}

	q := r.URL.Query()
	if q.Get("category") == "" {
		q.Add(provider.CategoryKey, category)
	}
	r.URL.RawQuery = q.Encode()

	p.Login(a.env, w, r)
}
