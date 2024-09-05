package authentication

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"

	"gitlab.com/isard/isardvdi-sdk-go"
)

type apiRegisterUserRsp struct {
	ID string `json:"id"`
}

func (a *Authentication) registerUser(u *model.User) error {
	tkn, err := token.SignRegisterToken(a.Secret, u)
	if err != nil {
		return err
	}

	id, err := a.API.AdminUserAutoRegister(context.Background(), tkn, string(u.Role), u.Group)
	if err != nil {
		return fmt.Errorf("register the user: %w", err)
	}

	u.ID = id
	u.Active = true

	return nil
}

func (a *Authentication) registerGroup(g *model.Group) error {
	grp, err := a.API.AdminGroupCreate(
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
