package api

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/gorilla/mux"
	"github.com/isard-vdi/isard/backend/model"
)

func checkDeploymentAuthorizationByID(u *model.User, id string) error {
	found := false
	for _, deployment := range u.Deployments {
		if deployment.ID == id {
			found = true
			break
		}
	}

	if !found {
		return errors.New("permission denied")
	}

	return nil
}

func (a *API) deployments(w http.ResponseWriter, r *http.Request) {
	u := getUsr(r.Context())
	/*
		json.Marshal returns null if desktops are an empty array
		See also:
		https://github.com/golang/go/issues/27589
		https://github.com/golang/go/issues/37711
	*/
	var err error
	b := []byte("[]")
	if u.Deployments != nil {
		b, err = json.Marshal(u.Deployments)
		if err != nil {
			http.Error(w, "cannot encode deployments", http.StatusBadRequest)
			return
		}
	}

	a.env.Sugar.Infow("deployments",
		"usr", u.ID(),
	)

	w.Header().Set("Content-Type", "application/json")
	w.Write(b)
}

func (a *API) deployment(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	d, ok := vars["deployment"]
	if !ok {
		http.Error(w, "unknown deployment", http.StatusBadRequest)
		return
	}

	u := getUsr(r.Context())
	if err := checkDeploymentAuthorizationByID(u, d); err != nil {
		http.Error(w, err.Error(), http.StatusForbidden)
		return
	}

	deployment, err := a.env.Isard.DeploymentGet(u, d)
	if err != nil {
		handleErr(err, w, r)
		return
	}

	a.env.Sugar.Infow("deployment",
		"usr", u.ID(),
	)

	w.Header().Set("Content-Type", "application/json")
	w.Write(deployment)
}
