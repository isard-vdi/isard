package authentication

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/model"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
)

func (a *Authentication) registerUser(ctx context.Context, u *model.User) error {
	// TODO: Register-Claims header (review #1) — out of scope for this refactor
	rsp, err := a.API.AdminAutoRegister(ctx, &apiv4.AutoRegisterRequest{
		RoleID:          string(u.Role),
		GroupID:         u.Group,
		SecondaryGroups: u.SecondaryGroups,
	})
	if err != nil {
		return fmt.Errorf("register the user: %w", err)
	}

	autoReg, ok := rsp.(*apiv4.AutoRegisterResponse)
	if !ok {
		return fmt.Errorf("register the user: %w", ogenclient.AsAPIError(rsp))
	}

	u.ID = autoReg.ID
	u.Active = true

	return nil
}

func (a *Authentication) registerGroup(ctx context.Context, g *model.Group) error {
	rsp, err := a.API.AdminCreateGroup(
		ctx,
		&apiv4.AdminGroupCreateData{
			UID:            apiv4.NewOptString(g.Name),
			Name:           g.Name,
			Description:    apiv4.NewOptString(g.Description),
			ParentCategory: apiv4.NewOptString(g.Category),
			ExternalAppID:  apiv4.NewOptString(g.ExternalAppID),
			ExternalGid:    apiv4.NewOptString(g.ExternalGID),
		},
	)
	if err != nil {
		return fmt.Errorf("register the group: %w", err)
	}

	grp, ok := rsp.(*apiv4.AdminGroup)
	if !ok {
		return fmt.Errorf("register the group: %w", ogenclient.AsAPIError(rsp))
	}

	g.ID = grp.ID
	g.UID = grp.UID.Or("")

	return nil
}
