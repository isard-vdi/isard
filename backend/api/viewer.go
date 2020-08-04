package api

import (
	"net/http"
)

type viewerResponse struct {
	Type    string `json:"type,omitempty"`
	Content string `json:"content,omitempty"`
}

func (a *API) viewer(w http.ResponseWriter, r *http.Request) {
	const (
		viewerKey = "type"
	)

	u := getUsr(r.Context())
	vType := r.URL.Query().Get(viewerKey)

	c, err := getCookie(r)
	if err != nil {
		handleErr(err, w, r)
	}

	switch vType {
	case "remote":
		viewer, err := a.env.Isard.ViewerRemote(c.DesktopID)
		if err != nil {
			handleErr(err, w, r)
			return
		}

		c.RemoteViewer = viewer

	case "html":
		viewer, err := a.env.Isard.ViewerHTML(c.DesktopID)
		if err != nil {
			handleErr(err, w, r)
			return
		}

		c.WebViewer = viewer
	}

	if err := c.save(w); err != nil {
		handleErr(err, w, r)
		return
	}

	a.env.Sugar.Infow("viewer",
		"type", vType,
		"usr", u.ID(),
	)

	w.WriteHeader(http.StatusOK)
}
