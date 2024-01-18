package authentication

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"

	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/model"

	"gitlab.com/isard/isardvdi-sdk-go"
)

type apiRegisterUserRsp struct {
	ID string `json:"id"`
}

// TODO: Make this use the isardvdi-go-sdk and the pkg/jwt package
func (a *Authentication) registerUser(u *model.User) error {
	tkn, err := token.SignRegisterToken(a.Secret, a.Duration, u)
	if err != nil {
		return err
	}

	login, err := token.SignLoginToken(a.Secret, a.Duration, u)
	if err != nil {
		return err
	}

	req, err := http.NewRequest(http.MethodPost, "http://isard-api:5000/api/v3/user/auto-register", nil)
	if err != nil {
		return fmt.Errorf("create http request: %w", err)
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", tkn))
	req.Header.Set("Login-Claims", fmt.Sprintf("Bearer %s", login))

	rsp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("do http request: %w", err)
	}

	if rsp.StatusCode != 200 {
		return fmt.Errorf("http code not 200: %d", rsp.StatusCode)
	}

	r := &apiRegisterUserRsp{}
	defer rsp.Body.Close()
	if err := json.NewDecoder(rsp.Body).Decode(r); err != nil {
		return fmt.Errorf("parse auto register JSON response: %w", err)
	}
	u.ID = r.ID
	u.Active = true

	return nil
}

func (a *Authentication) registerGroup(g *model.Group) error {
	grp, err := a.Client.AdminGroupCreate(
		context.Background(),
		g.Category,
		// TODO: When UUIDs arrive, this g.Name has to be removed and the dependency has to be updated to v0.14.1
		g.Name,
		g.Name,
		g.Description,
		g.ExternalAppID,
		g.ExternalGID,
	)
	if err != nil {
		return fmt.Errorf("register the group: %w", err)
	}

	g.ID = isardvdi.GetString(grp.ID)
	g.UID = isardvdi.GetString(grp.UID)

	return nil
}
