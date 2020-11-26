package api

import (
	"encoding/json"
	"net/http"
)

func (a *API) configuration(w http.ResponseWriter, r *http.Request) {
	b, err := json.Marshal(a.env.Cfg.Frontend)
	if err != nil {
		http.Error(w, "marshal frontend configuration", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	w.Header().Set("Content-Type", "application/json")
	w.Write(b)
}
