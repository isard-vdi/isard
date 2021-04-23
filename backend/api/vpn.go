package api

import (
	"net/http"
)

func (a *API) vpn(w http.ResponseWriter, r *http.Request) {
	u := getUsr(r.Context())
	a.env.Sugar.Infow("vpn",
		"usr", u.ID(),
	)
	viewer, err := a.env.Isard.Vpn(u)
	if err != nil {
		handleErr(err, w, r)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Write(viewer)
}
