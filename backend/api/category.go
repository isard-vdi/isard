package api

import (
	"net/http"

	"github.com/gorilla/mux"
)

func (a *API) category(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	category, _ := vars["category"]
	if category == "" {
		category = "default"
	}

	a.env.Isard.CategoryLoad(category, w, r)
}
