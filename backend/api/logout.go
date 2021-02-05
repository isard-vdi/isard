package api

import (
	"net/http"

	"github.com/isard-vdi/isard/backend/auth/provider"
)

func (a *API) logout(w http.ResponseWriter, r *http.Request) {
	c, err := getCookie(r)
	if err == nil {
		user := getUsr(r.Context())
		for _, desktop := range user.Desktops {
			if desktop.Type == "nonpersistent" {
				if err := a.env.Isard.DesktopDelete(desktop.ID); err != nil {
					a.env.Sugar.Errorw("delete desktop",
						"err", err,
						"id", desktop.ID,
					)
				}
			}
		}
	}

	// Delete the user info cookie
	delCookie(w, r)

	// Delete the session cookie
	s, _ := a.env.Auth.SessStore.Get(r, provider.SessionStoreKey)
	if !s.IsNew {
		s.Options.MaxAge = -1

		if err := s.Save(r, w); err != nil {
			a.env.Sugar.Errorw("get user session",
				"err", err,
				"id", c.DesktopID,
			)

			http.Redirect(w, r, "/", http.StatusFound)
		}
	}

	u := getUsr(r.Context())
	a.env.Sugar.Infow("logout",
		"usr", u.ID(),
	)

	http.Redirect(w, r, "/", http.StatusFound)
}
