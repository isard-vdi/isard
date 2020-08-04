package api

import (
	"net/http"
)

const (
	createTemplateKey = "template"
)

func (a *API) create(w http.ResponseWriter, r *http.Request) {
	u := getUsr(r.Context())
	tmpl := r.FormValue(createTemplateKey)

	c, err := getCookie(r)
	if err != nil {
		c = &cookie{}
	}

	id, err := a.env.Isard.DesktopCreate(u, tmpl, false)
	if err != nil {
		handleErr(err, w, r)
		return
	}

	c.DesktopID = id
	if err := c.update(u, w); err != nil {
		handleErr(err, w, r)
		return
	}

	w.WriteHeader(http.StatusCreated)
}
