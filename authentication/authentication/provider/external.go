package provider

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/model"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type External struct {
	db r.QueryExecutor
}

func checkRequiredArgs(args map[string]string) error {
	var requiredArgs = []string{TokenArgsKey}

request:
	for _, rA := range requiredArgs {
		for a := range args {
			if a == rA && a != "" {
				continue request
			}
		}

		return fmt.Errorf("missing required argument: '%s'", rA)
	}

	return nil
}

func (e *External) Login(ctx context.Context, categoryID string, args map[string]string) (*model.Group, *model.User, string, error) {
	if err := checkRequiredArgs(args); err != nil {
		return nil, nil, "", err
	}

	claims, err := token.ParseExternalToken(e.db, args[TokenArgsKey])
	if err != nil {
		return nil, nil, "", err
	}

	if model.Role(claims.Role).HasEqualOrMorePrivileges(model.RoleAdmin) {
		return nil, nil, "", errors.New("cannot create an admin user through an external app")
	}

	g := &model.Group{
		Category:      claims.CategoryID,
		ExternalAppID: claims.KeyID,
		ExternalGID:   claims.GroupID,
	}

	// We can safely set this parameters, since they're not going to be overrided if the group exists
	g.Description = "This is a auto register created by the authentication service. This group maps a group of an external app"
	g.GenerateNameExternal(e.String())

	u := &model.User{
		UID:      claims.UserID,
		Username: claims.Username,
		Provider: fmt.Sprintf("%s_%s", e.String(), claims.KeyID),

		Category: claims.CategoryID,
		Role:     model.Role(claims.Role),

		Name:  claims.Name,
		Email: claims.Email,
		Photo: claims.Photo,
	}

	return g, u, "", nil
}

func (External) Callback(context.Context, *token.CallbackClaims, map[string]string) (*model.Group, *model.User, string, error) {
	return nil, nil, "", errInvalidIDP
}

func (External) AutoRegister() bool {
	return true
}

func (External) String() string {
	return types.External
}
