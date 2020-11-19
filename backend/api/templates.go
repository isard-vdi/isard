package api

import (
	"net/http"
	"encoding/json"
)

func (a *API) templates(w http.ResponseWriter, r *http.Request) {
	u := getUsr(r.Context())
	/*
		json.Marshal returns null if templates are an empty array
		See also:
		https://github.com/golang/go/issues/27589
		https://github.com/golang/go/issues/37711
	*/
	var err error
	b := []byte("[]")
	if u.Templates != nil {
		b, err = json.Marshal(u.Templates)
		if err != nil {
			http.Error(w, "cannot encode templates", http.StatusBadRequest)
			return
		}
	}
	w.Header().Set("Content-Type", "application/json")
	w.Write(b)
}
