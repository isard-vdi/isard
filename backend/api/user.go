package api

import (
	"encoding/json"
	"net/http"
)

func (a *API) user(w http.ResponseWriter, r *http.Request) {
	u := getUsr(r.Context())
	b, err := json.Marshal(u)
	if err != nil {
		http.Error(w, "cannot encode user", http.StatusBadRequest)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Write(b)
}
